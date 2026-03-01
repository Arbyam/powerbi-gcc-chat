"""
Unified Security Layer — integrates PII detection and audit logging.
"""
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from .pii_detector import PIIDetector, MaskingStrategy
from .audit_logger import AuditLogger, AuditEventType, get_audit_logger

logger = logging.getLogger(__name__)


class SecurityLayer:
    def __init__(self, enable_pii_detection: bool = True, enable_audit: bool = True):
        self.pii_detector = PIIDetector(default_strategy=MaskingStrategy.PARTIAL) if enable_pii_detection else None
        self.audit_logger = get_audit_logger() if enable_audit else None
        logger.info("Security layer initialized (PII=%s, Audit=%s)", enable_pii_detection, enable_audit)

    def process_results(
        self,
        results: List[Dict[str, Any]],
        query: str = "",
        source: str = "cloud",
        duration_ms: Optional[float] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        report: Dict[str, Any] = {"pii_detected": False, "pii_count": 0, "pii_types": []}

        processed = results
        if self.pii_detector and results:
            processed, pii_summary = self.pii_detector.process_results(results)
            report["pii_detected"] = pii_summary["total_detections"] > 0
            report["pii_count"] = pii_summary["total_detections"]
            report["pii_types"] = pii_summary["types_detected"]

        if self.audit_logger:
            self.audit_logger.log_query(
                query=query, source=source, result_count=len(results),
                duration_ms=duration_ms, success=success, error_message=error_message,
                pii_detected=report["pii_detected"], pii_types=report["pii_types"],
            )

        return processed, report


_security_layer: Optional[SecurityLayer] = None


def get_security_layer() -> SecurityLayer:
    global _security_layer
    if _security_layer is None:
        _security_layer = SecurityLayer()
    return _security_layer
