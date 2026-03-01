"""
Power BI GCC Chat — FastAPI Backend
Provides REST API endpoints for the React frontend to interact with
Azure OpenAI + Power BI tools.
"""
import logging
import os
import sys
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Dict, List, Optional

from .config import get_settings
from .orchestrator import Orchestrator

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("powerbi-gcc-chat")

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Power BI GCC Chat API",
    description="Chat with your Power BI data using Azure OpenAI. Supports Commercial, GCC, and GCC High.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Container Apps handles CORS at ingress level
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lazy-init orchestrator (needs env vars)
_orchestrator: Optional[Orchestrator] = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., description="Conversation history")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for tracking")
    stream: bool = Field(False, description="Whether to stream the response via SSE")


class ChatResponse(BaseModel):
    response: str
    tools_called: List[str] = []
    conversation_id: Optional[str] = None


class DaxRequest(BaseModel):
    workspace_id: str
    dataset_id: str
    dax_query: str


class HealthResponse(BaseModel):
    status: str
    version: str
    cloud_environment: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="healthy",
        version="2.0.0",
        cloud_environment=settings.cloud_environment.value,
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Chat with Power BI data using Azure OpenAI."""
    try:
        orch = get_orchestrator()
        msgs = [m.model_dump() for m in request.messages]
        conv_id = request.conversation_id or str(uuid.uuid4())

        if request.stream:
            return StreamingResponse(
                orch.chat_stream(msgs, conversation_id=conv_id),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        result = await orch.chat(msgs, conversation_id=conv_id)
        return ChatResponse(**result)
    except Exception as e:
        logger.error("Chat error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workspaces")
async def list_workspaces():
    """List Power BI workspaces."""
    from .tools.rest_connector import PowerBIRestConnector
    pbi = PowerBIRestConnector()
    workspaces = pbi.list_workspaces()
    return {"workspaces": workspaces}


@app.get("/api/datasets/{workspace_id}")
async def list_datasets(workspace_id: str):
    """List datasets in a workspace."""
    from .tools.rest_connector import PowerBIRestConnector
    pbi = PowerBIRestConnector()
    datasets = pbi.list_datasets(workspace_id)
    return {"datasets": datasets}


@app.post("/api/query")
async def execute_query(request: DaxRequest):
    """Execute a DAX query directly (bypasses AI orchestration)."""
    from .tools.rest_connector import PowerBIRestConnector
    from .tools.security import get_security_layer
    import time

    pbi = PowerBIRestConnector()
    security = get_security_layer()

    start = time.time()
    raw = pbi.execute_dax(request.workspace_id, request.dataset_id, request.dax_query)
    duration = (time.time() - start) * 1000

    if "error" in raw:
        raise HTTPException(status_code=400, detail=raw["error"])

    if raw.get("rows"):
        processed, report = security.process_results(
            raw["rows"], query=request.dax_query, source="cloud", duration_ms=duration
        )
        raw["rows"] = processed
        raw["security"] = report

    return raw


@app.get("/api/config")
async def get_config():
    """Return non-sensitive config for the frontend."""
    return {
        "cloud_environment": settings.cloud_environment.value,
        "max_dax_rows": settings.max_dax_rows,
        "pii_detection_enabled": settings.enable_pii_detection,
        "audit_enabled": settings.enable_audit,
    }
