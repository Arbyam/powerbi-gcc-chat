"""
PII Detection and Auto-Masking Module
Ported from powerbi-mcp v1 — detects and masks PII in Power BI query results.
"""
import re
import hashlib
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class MaskingStrategy(Enum):
    FULL = "full"
    PARTIAL = "partial"
    HASH = "hash"
    REDACT = "redact"
    NONE = "none"


class PIIType(Enum):
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    EMAIL = "email"
    PHONE = "phone"
    IP_ADDRESS = "ip_address"
    DATE_OF_BIRTH = "date_of_birth"
    NAME = "name"


PII_PATTERNS = {
    PIIType.SSN: [r'\b\d{3}-\d{2}-\d{4}\b', r'\b\d{3}\s\d{2}\s\d{4}\b'],
    PIIType.CREDIT_CARD: [
        r'\b4\d{3}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
        r'\b5[1-5]\d{2}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
        r'\b3[47]\d{2}[-\s]?\d{6}[-\s]?\d{5}\b',
    ],
    PIIType.EMAIL: [r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'],
    PIIType.PHONE: [r'\b\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'],
    PIIType.IP_ADDRESS: [r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b'],
    PIIType.DATE_OF_BIRTH: [r'\b(?:0[1-9]|1[0-2])[/-](?:0[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}\b'],
}

PII_COLUMN_INDICATORS = {
    PIIType.SSN: ["ssn", "social_security"],
    PIIType.EMAIL: ["email", "e_mail", "email_address", "mail"],
    PIIType.PHONE: ["phone", "telephone", "mobile", "cell"],
    PIIType.NAME: ["name", "first_name", "last_name", "customer_name", "employee_name", "fullname"],
    PIIType.DATE_OF_BIRTH: ["dob", "birth_date", "birthdate", "date_of_birth", "birthday"],
    PIIType.IP_ADDRESS: ["ip", "ip_address", "client_ip"],
    PIIType.CREDIT_CARD: ["credit_card", "card_number", "cc_number"],
}


class PIIDetector:
    def __init__(
        self,
        default_strategy: MaskingStrategy = MaskingStrategy.PARTIAL,
        enabled_types: Optional[List[PIIType]] = None,
        column_overrides: Optional[Dict[str, MaskingStrategy]] = None,
    ):
        self.default_strategy = default_strategy
        self.enabled_types = enabled_types or list(PIIType)
        self.column_overrides = column_overrides or {}
        self._compiled = {
            pt: [re.compile(p, re.IGNORECASE) for p in patterns]
            for pt, patterns in PII_PATTERNS.items()
            if pt in self.enabled_types
        }

    def detect_pii_type_from_column(self, column_name: str) -> Optional[PIIType]:
        col = column_name.lower().strip("[]")
        for pt, indicators in PII_COLUMN_INDICATORS.items():
            if any(ind in col or col in ind for ind in indicators):
                return pt
        return None

    def detect_pii_in_value(self, value: str) -> List[Tuple[PIIType, str, int, int]]:
        if not isinstance(value, str):
            return []
        hits: List[Tuple[PIIType, str, int, int]] = []
        for pt, patterns in self._compiled.items():
            for pat in patterns:
                for m in pat.finditer(value):
                    hits.append((pt, m.group(), m.start(), m.end()))
        return hits

    def mask_value(self, value: str, pii_type: PIIType, strategy: Optional[MaskingStrategy] = None) -> str:
        s = strategy or self.default_strategy
        if s == MaskingStrategy.NONE:
            return value
        if s == MaskingStrategy.REDACT:
            return f"[REDACTED-{pii_type.value.upper()}]"
        if s == MaskingStrategy.HASH:
            return f"[HASH:{hashlib.sha256(value.encode()).hexdigest()[:12]}]"
        if s == MaskingStrategy.FULL:
            return "*" * min(len(value), 10)
        # PARTIAL
        return self._partial_mask(value, pii_type)

    def _partial_mask(self, value: str, pii_type: PIIType) -> str:
        if pii_type == PIIType.EMAIL and "@" in value:
            local, domain = value.rsplit("@", 1)
            parts = domain.rsplit(".", 1)
            if len(parts) == 2:
                return f"{local[0]}***@{parts[0][0]}****.{parts[1]}"
            return f"{local[0]}***@***.***"
        if pii_type == PIIType.PHONE:
            digits = re.sub(r"\D", "", value)
            return f"(***) ***-{digits[-4:]}" if len(digits) >= 4 else "***-***-****"
        if pii_type == PIIType.SSN:
            digits = re.sub(r"\D", "", value)
            return f"***-**-{digits[-4:]}" if len(digits) >= 4 else "***-**-****"
        if pii_type == PIIType.CREDIT_CARD:
            digits = re.sub(r"\D", "", value)
            return f"****-****-****-{digits[-4:]}" if len(digits) >= 4 else "****-****-****-****"
        if pii_type == PIIType.NAME:
            return " ".join(f"{w[0]}{'*' * (len(w) - 1)}" if len(w) > 1 else "*" for w in value.split())
        if pii_type == PIIType.IP_ADDRESS:
            parts = value.split(".")
            return f"{parts[0]}.{parts[1]}.***.***" if len(parts) == 4 else "***.***.***.***"
        if len(value) > 2:
            return f"{value[0]}{'*' * (len(value) - 2)}{value[-1]}"
        return "*" * len(value)

    def process_value(self, value: Any, column_name: Optional[str] = None) -> Tuple[Any, List[Dict]]:
        if value is None or not isinstance(value, str):
            return value, []
        detections: List[Dict] = []
        if column_name:
            col_pii = self.detect_pii_type_from_column(column_name)
            if col_pii and col_pii in self.enabled_types:
                strat = self.column_overrides.get(column_name.lower().strip("[]"), self.default_strategy)
                detections.append({"type": col_pii.value, "source": "column_name", "column": column_name})
                return self.mask_value(value, col_pii, strat), detections
        pii_found = self.detect_pii_in_value(value)
        if pii_found:
            processed = value
            for pt, matched, start, end in sorted(pii_found, key=lambda x: x[2], reverse=True):
                strat = self.column_overrides.get(column_name.lower().strip("[]") if column_name else "", self.default_strategy)
                masked = self.mask_value(matched, pt, strat)
                processed = processed[:start] + masked + processed[end:]
                detections.append({"type": pt.value, "source": "pattern", "column": column_name, "masked": masked})
            return processed, detections
        return value, []

    def process_results(self, results: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        all_dets: List[Dict] = []
        out: List[Dict[str, Any]] = []
        for row in results:
            new_row = {}
            for col, val in row.items():
                pv, dets = self.process_value(val, col)
                new_row[col] = pv
                all_dets.extend(dets)
            out.append(new_row)
        summary = {
            "total_detections": len(all_dets),
            "types_detected": list({d["type"] for d in all_dets}),
            "detections": all_dets[:10],
        }
        if all_dets:
            logger.info("PII Detection: %d instances found", len(all_dets))
        return out, summary


def mask_pii(results: List[Dict[str, Any]], strategy: MaskingStrategy = MaskingStrategy.PARTIAL) -> List[Dict[str, Any]]:
    d = PIIDetector(default_strategy=strategy)
    processed, _ = d.process_results(results)
    return processed
