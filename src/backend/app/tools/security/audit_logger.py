"""
Audit Logger — JSON-structured query audit logging for compliance.
"""
import json
import hashlib
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    QUERY_EXECUTE = "query_execute"
    QUERY_SUCCESS = "query_success"
    QUERY_FAILURE = "query_failure"
    CONNECTION = "connection"
    PII_DETECTED = "pii_detected"
    ACCESS_DENIED = "access_denied"
    CHAT_MESSAGE = "chat_message"


class AuditLogger:
    def __init__(self, log_dir: Optional[str] = None, include_query_text: bool = True, redact_sensitive: bool = True):
        self.log_dir = Path(log_dir) if log_dir else Path(__file__).parent.parent.parent.parent / "logs"
        self.log_file = self.log_dir / "audit.log"
        self.include_query_text = include_query_text
        self.redact_sensitive = redact_sensitive
        self._lock = threading.Lock()
        self._session_id = hashlib.sha256(f"{datetime.now(timezone.utc).isoformat()}{os.getpid()}".encode()).hexdigest()[:16]
        self._count = 0
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log_event(self, event_type: AuditEventType, message: str = "", details: Optional[Dict[str, Any]] = None):
        self._count += 1
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self._session_id,
            "event_id": f"{self._session_id}_{self._count}",
            "event_type": event_type.value,
            "message": message,
            "details": details or {},
        }
        with self._lock:
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event, default=str) + "\n")
            except Exception as e:
                logger.error("Audit write failed: %s", e)

    def log_query(self, query: str, source: str = "cloud", result_count: Optional[int] = None,
                  duration_ms: Optional[float] = None, success: bool = True, error_message: Optional[str] = None,
                  pii_detected: bool = False, pii_types: Optional[List[str]] = None):
        et = AuditEventType.QUERY_SUCCESS if success else AuditEventType.QUERY_FAILURE
        self.log_event(et, message=f"DAX query {'succeeded' if success else 'failed'}", details={
            "query": query if self.include_query_text else "[REDACTED]",
            "query_fingerprint": hashlib.sha256(query.lower().encode()).hexdigest()[:12],
            "source": source,
            "result_count": result_count,
            "duration_ms": duration_ms,
            "error": error_message,
            "pii_detected": pii_detected,
            "pii_types": pii_types or [],
        })

    def log_chat(self, user_message: str, assistant_response: str, tools_called: Optional[List[str]] = None):
        self.log_event(AuditEventType.CHAT_MESSAGE, message="Chat interaction", details={
            "user_message_length": len(user_message),
            "response_length": len(assistant_response),
            "tools_called": tools_called or [],
        })


_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
