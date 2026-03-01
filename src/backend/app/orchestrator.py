"""
Azure OpenAI Orchestrator
Takes user natural-language questions, uses Azure OpenAI function calling to invoke
Power BI tools, and returns conversational answers grounded in real data.
"""
import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from openai import AsyncAzureOpenAI

from .config import get_settings
from .tools.rest_connector import PowerBIRestConnector
from .tools.security import get_security_layer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions for Azure OpenAI function calling
# ---------------------------------------------------------------------------

TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_workspaces",
            "description": "List all Power BI workspaces accessible by the service principal.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_datasets",
            "description": "List all datasets (semantic models) in a Power BI workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "The workspace/group GUID."}
                },
                "required": ["workspace_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_reports",
            "description": "List all reports in a Power BI workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "The workspace/group GUID."}
                },
                "required": ["workspace_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_dax",
            "description": (
                "Execute a DAX query against a Power BI dataset. "
                "Use this to answer data questions. The query MUST start with EVALUATE. "
                "Example: EVALUATE SUMMARIZECOLUMNS('Date'[Year], \"Total Sales\", SUM('Sales'[Amount]))"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "The workspace/group GUID."},
                    "dataset_id": {"type": "string", "description": "The dataset/semantic model GUID."},
                    "dax_query": {"type": "string", "description": "A valid DAX query starting with EVALUATE."},
                },
                "required": ["workspace_id", "dataset_id", "dax_query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tables_and_columns",
            "description": "Discover the tables and columns in a Power BI dataset to understand its schema before writing DAX.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "The workspace/group GUID."},
                    "dataset_id": {"type": "string", "description": "The dataset/semantic model GUID."},
                },
                "required": ["workspace_id", "dataset_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_measures",
            "description": "Discover measures (calculated fields) defined in a Power BI dataset.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "The workspace/group GUID."},
                    "dataset_id": {"type": "string", "description": "The dataset/semantic model GUID."},
                },
                "required": ["workspace_id", "dataset_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "refresh_dataset",
            "description": "Trigger a refresh for a Power BI dataset.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "The workspace/group GUID."},
                    "dataset_id": {"type": "string", "description": "The dataset/semantic model GUID."},
                },
                "required": ["workspace_id", "dataset_id"],
            },
        },
    },
]

SYSTEM_PROMPT = """\
You are a Power BI data analyst assistant. You help users explore and query their Power BI data
using natural language. You have access to tools that can:

1. List workspaces, datasets, and reports
2. Discover dataset schemas (tables, columns, measures)
3. Execute DAX queries against datasets
4. Trigger dataset refreshes

**Workflow for answering data questions:**
1. If you don't know the workspace/dataset IDs yet, first call list_workspaces, then list_datasets.
2. Before writing DAX, call get_tables_and_columns and get_measures to understand the schema.
3. Write a valid DAX query using EVALUATE and call execute_dax.
4. Summarize the results in a clear, conversational response with the key data points.

**Important rules:**
- Always use EVALUATE at the start of DAX queries.
- Prefer SUMMARIZECOLUMNS for aggregations.
- Quote table names in single quotes: 'TableName'.
- Quote column names in brackets: [ColumnName].
- If a query fails, examine the error and try correcting it.
- Format numbers and dates clearly in your responses.
- If results contain sensitive data, note that PII masking is applied automatically.
"""


class Orchestrator:
    """Coordinates Azure OpenAI and Power BI tools to answer user questions."""

    def __init__(self):
        settings = get_settings()
        self.client = AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_key or None,
            api_version=settings.azure_openai_api_version,
        )
        self.deployment = settings.azure_openai_deployment
        self.pbi = PowerBIRestConnector()
        self.security = get_security_layer()
        self.max_tool_rounds = 6  # prevent infinite loops

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------

    def _call_tool(self, name: str, args: Dict[str, Any]) -> str:
        """Execute a tool and return JSON result."""
        start = time.time()
        try:
            if name == "list_workspaces":
                result = self.pbi.list_workspaces()
            elif name == "list_datasets":
                result = self.pbi.list_datasets(**args)
            elif name == "list_reports":
                result = self.pbi.list_reports(**args)
            elif name == "execute_dax":
                raw = self.pbi.execute_dax(**args)
                # Apply security layer (PII masking)
                if "rows" in raw and raw["rows"]:
                    processed, report = self.security.process_results(
                        raw["rows"],
                        query=args.get("dax_query", ""),
                        source="cloud",
                        duration_ms=(time.time() - start) * 1000,
                    )
                    raw["rows"] = processed
                    raw["security"] = report
                result = raw
            elif name == "get_tables_and_columns":
                result = self.pbi.get_tables_and_columns(**args)
            elif name == "get_measures":
                result = self.pbi.get_measures(**args)
            elif name == "refresh_dataset":
                result = self.pbi.refresh_dataset(**args)
            else:
                result = {"error": f"Unknown tool: {name}"}
        except Exception as e:
            logger.error("Tool %s failed: %s", name, e)
            result = {"error": str(e)}

        return json.dumps(result, default=str)

    # ------------------------------------------------------------------
    # Chat (non-streaming)
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: List[Dict[str, str]],
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process a chat turn — may call tools multiple times until
        Azure OpenAI returns a final text response.
        """
        # Prepend system prompt
        full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
        tools_called: List[str] = []

        for _ in range(self.max_tool_rounds):
            response = await self.client.chat.completions.create(
                model=self.deployment,
                messages=full_messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.1,
                max_tokens=4096,
            )

            choice = response.choices[0]

            # If the model wants to call tools
            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                # Add assistant message (with tool_calls)
                full_messages.append(choice.message.model_dump())

                for tc in choice.message.tool_calls:
                    fn_name = tc.function.name
                    fn_args = json.loads(tc.function.arguments)
                    logger.info("Tool call: %s(%s)", fn_name, fn_args)
                    tools_called.append(fn_name)

                    result_str = self._call_tool(fn_name, fn_args)
                    full_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_str,
                    })
            else:
                # Final text response
                content = choice.message.content or ""

                # Audit the chat interaction
                if self.security.audit_logger:
                    user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
                    self.security.audit_logger.log_chat(user_msg, content, tools_called)

                return {
                    "response": content,
                    "tools_called": tools_called,
                    "conversation_id": conversation_id,
                }

        return {
            "response": "I reached the maximum number of tool calls. Please try rephrasing your question.",
            "tools_called": tools_called,
            "conversation_id": conversation_id,
        }

    # ------------------------------------------------------------------
    # Chat (streaming)
    # ------------------------------------------------------------------

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        conversation_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream a chat response. Yields SSE-formatted data chunks.
        Tool calls are handled internally; only final text tokens are streamed.
        """
        full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
        tools_called: List[str] = []

        for _ in range(self.max_tool_rounds):
            # First pass: non-streaming to check for tool calls
            response = await self.client.chat.completions.create(
                model=self.deployment,
                messages=full_messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.1,
                max_tokens=4096,
            )
            choice = response.choices[0]

            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                full_messages.append(choice.message.model_dump())
                for tc in choice.message.tool_calls:
                    fn_name = tc.function.name
                    fn_args = json.loads(tc.function.arguments)
                    tools_called.append(fn_name)
                    # Emit a status event so the frontend knows we're working
                    yield f"data: {json.dumps({'type': 'tool_call', 'tool': fn_name})}\n\n"
                    result_str = self._call_tool(fn_name, fn_args)
                    full_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_str,
                    })
            else:
                # Final response — now stream it
                stream = await self.client.chat.completions.create(
                    model=self.deployment,
                    messages=full_messages,
                    stream=True,
                    temperature=0.1,
                    max_tokens=4096,
                )
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        token = chunk.choices[0].delta.content
                        yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

                yield f"data: {json.dumps({'type': 'done', 'tools_called': tools_called})}\n\n"
                return

        yield f"data: {json.dumps({'type': 'error', 'message': 'Max tool rounds reached'})}\n\n"
