"""
Log / plain-text evidence parser.

Handles:
  - Structured service event logs (.log)
  - Syslog archives (.log)
  - Application trace logs (.log)
  - Support replica logs (.log)
  - Any .txt plain-text evidence file

Each non-empty line is treated as one EvidenceRecord.  The parser attempts
to extract:
  - ISO-8601 timestamps
  - User identifiers (user_id, email, email_hash)
  - Resource IDs
  - System/source identifiers from filename hints

Owned by: Member 2 — Chinmay Motagi
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from code.models.enums import EvidenceFormat
from code.models.schemas import EvidenceFileEntry, EvidenceRecord
from code.parsers.common import (
    build_base_record,
    extract_identifiers,
    infer_record_type_and_system,
    safe_parse_datetime,
)

logger = logging.getLogger(__name__)

# Regex patterns for log-line extraction
_ISO_TS_RE = re.compile(
    r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?'
)
_EMAIL_RE = re.compile(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}')
_EMAIL_HASH_RE = re.compile(r'\b[0-9a-f]{64}\b')
_USER_ID_RE = re.compile(r'\b(user_\d+)\b')
_RESOURCE_ID_RE = re.compile(
    r'\b(account_\d+|search_\d+|support_\d+|export_\d+|analytics_\d+|'
    r'backup_\d+|data_flow_\d+|audit_record_\d+|tombstone_\d+|'
    r'connector_\d+|marketing_\d+|search_\w+|email_delivery_\w+|'
    r'activity_\d+|audit_\d+)\b'
)


def parse_log_evidence(
    abs_path: Path,
    entry: EvidenceFileEntry,
    fmt: EvidenceFormat,
) -> list[EvidenceRecord]:
    """
    Parse a structured or unstructured log / text evidence file.

    Each non-empty line produces one EvidenceRecord.  The parser does
    best-effort extraction of timestamps, identifiers, and resource IDs
    via regular expressions.
    """
    records: list[EvidenceRecord] = []

    try:
        lines = abs_path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except Exception as exc:  # noqa: BLE001
        logger.error("Cannot read log file %s: %s", abs_path, exc)
        return records

    for i, line in enumerate(lines):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        try:
            # Build a pseudo-dict from extracted fragments for common helpers
            flat: dict[str, str] = {"_raw_line": line}

            # Timestamp
            ts_match = _ISO_TS_RE.search(line)
            if ts_match:
                flat["event_time"] = ts_match.group(0)

            # Identifiers
            user_match = _USER_ID_RE.search(line)
            if user_match:
                flat["user_id"] = user_match.group(1)

            email_match = _EMAIL_RE.search(line)
            if email_match:
                flat["email"] = email_match.group(0).lower()

            hash_match = _EMAIL_HASH_RE.search(line)
            if hash_match:
                flat["email_hash"] = hash_match.group(0)

            # Resource ID
            res_match = _RESOURCE_ID_RE.search(line)
            if res_match:
                flat["resource_id"] = res_match.group(0)

            base = build_base_record(entry, fmt)
            ids = extract_identifiers(flat)
            rtype, sys_id = infer_record_type_and_system(flat, entry)
            ts = safe_parse_datetime(flat.get("event_time", ""))

            rec = EvidenceRecord(
                **base,
                record_type=rtype,
                system_id=sys_id,
                resource_id=flat.get("resource_id"),
                user_id=ids.get("user_id"),
                email=ids.get("email"),
                email_hash=ids.get("email_hash"),
                phone=ids.get("phone"),
                name=ids.get("name"),
                record_timestamp=ts,
                raw_fields=flat,
            )
            records.append(rec)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Log line %d in %s skipped: %s", i, entry.file_id, exc)

    return records
