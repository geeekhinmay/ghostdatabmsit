"""
Common utilities shared across all evidence parsers.

Provides:
  - build_base_record()      — builds the source-identity fields
  - extract_identifiers()    — extracts user_id, email, email_hash, phone, name
  - infer_record_type_and_system() — infers semantic category and system_id
  - safe_parse_datetime()    — parses ISO-8601 strings without raising

Owned by: Member 2 — Chinmay Motagi
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from code.models.enums import EvidenceFormat
from code.models.schemas import EvidenceFileEntry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Identity extraction patterns
# ---------------------------------------------------------------------------
_EMAIL_RE = re.compile(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}')
_EMAIL_HASH_RE = re.compile(r'\b[0-9a-f]{64}\b')
_USER_ID_RE = re.compile(r'\b(user_\d+)\b')
_PHONE_RE = re.compile(r'\+[\d\s\-().]{7,20}')

# ---------------------------------------------------------------------------
# Record-type inference: maps filename/origin/table patterns -> (rtype, sys_id)
# ---------------------------------------------------------------------------

_FILE_PATH_RULES: list[tuple[str, str, str]] = [
    # (path_substring, record_type, system_id)
    ("account",         "account",          "account_service"),
    ("search_index",    "search_index",     "search_service"),
    ("search",          "search_index",     "search_service"),
    ("support_replica", "support_message",  "support_platform"),
    ("support",         "support_message",  "support_platform"),
    ("analytics",       "analytics_profile","analytics_platform"),
    ("export",          "user_export",      "export_service"),
    ("marketing",       "marketing_profile","marketing_platform"),
    ("notification",    "email_log",        "notification_service"),
    ("email_delivery",  "email_log",        "email_delivery_service"),
    ("security_audit",  "security_audit",   "security_service"),
    ("security_retention","security_audit", "security_service"),
    ("legal_retention", "legal_hold",       "legal_retention_service"),
    ("backup",          "backup",           "backup_service"),
    ("connector",       "connector",        "integration_service"),
    ("tombstone",       "tombstone",        "identity_service"),
    ("deleted_account", "tombstone",        "identity_service"),
    ("service_resource","activity_event",   "unknown"),
    ("resource_lookup", "activity_event",   "unknown"),
    ("inventory",       "account",          "account_service"),
    ("failover",        "account",          "account_service"),
    ("regional_replica","account",          "account_service"),
    ("read_replica",    "account",          "account_service"),
    ("reporting_replica","account",         "account_service"),
]

# Table name rules for SQL parsing
_TABLE_RULES: list[tuple[str, str, str]] = [
    ("account",         "account",          "account_service"),
    ("search",          "search_index",     "search_service"),
    ("support",         "support_message",  "support_platform"),
    ("analytic",        "analytics_profile","analytics_platform"),
    ("export",          "user_export",      "export_service"),
    ("marketing",       "marketing_profile","marketing_platform"),
    ("email",           "email_log",        "email_delivery_service"),
    ("security",        "security_audit",   "security_service"),
    ("legal",           "legal_hold",       "legal_retention_service"),
    ("backup",          "backup",           "backup_service"),
    ("connector",       "connector",        "integration_service"),
    ("tombstone",       "tombstone",        "identity_service"),
    ("user",            "account",          "account_service"),
]


def build_base_record(entry: EvidenceFileEntry, fmt: EvidenceFormat) -> dict:
    """
    Build the source-identity portion of an EvidenceRecord (fields that come
    from the manifest, not the file content).
    """
    return {
        "file_id": entry.file_id,
        "file_path": entry.file_path,
        "file_format": fmt,
        "origin": entry.origin,
        "captured_at": entry.captured_at,
    }


def extract_identifiers(row: dict) -> dict[str, Optional[str]]:
    """
    Extract user identity fields from a flat dict (row or flattened JSON).

    Checks well-known column names first, then falls back to regex scanning
    all values.

    Returns a dict with keys: user_id, email, email_hash, phone, name.
    All values may be None if not found.
    """
    result: dict[str, Optional[str]] = {
        "user_id": None,
        "email": None,
        "email_hash": None,
        "phone": None,
        "name": None,
    }

    # Case-insensitive column lookup
    lower_row = {k.lower(): v for k, v in row.items() if isinstance(v, str)}

    # user_id
    for key in ("user_id", "userid", "customer_id", "subject_id"):
        if key in lower_row and _USER_ID_RE.match(lower_row[key].strip()):
            result["user_id"] = lower_row[key].strip()
            break

    # email
    for key in ("email", "email_address", "user_email", "customer_email"):
        if key in lower_row and lower_row[key].strip():
            val = lower_row[key].strip().lower()
            if _EMAIL_RE.match(val):
                result["email"] = val
                break
    if result["email"] is None:
        # Scan all values
        for v in lower_row.values():
            m = _EMAIL_RE.search(v)
            if m:
                result["email"] = m.group(0).lower()
                break

    # email_hash
    for key in ("email_hash", "hashed_email", "hash"):
        if key in lower_row:
            val = lower_row[key].strip()
            if _EMAIL_HASH_RE.match(val):
                result["email_hash"] = val
                break
    if result["email_hash"] is None:
        for v in lower_row.values():
            m = _EMAIL_HASH_RE.search(v)
            if m:
                result["email_hash"] = m.group(0)
                break

    # phone
    for key in ("phone", "phone_number", "mobile", "telephone"):
        if key in lower_row and lower_row[key].strip():
            result["phone"] = lower_row[key].strip()
            break
    if result["phone"] is None:
        for v in lower_row.values():
            m = _PHONE_RE.search(v)
            if m:
                result["phone"] = m.group(0).strip()
                break

    # name
    for key in ("name", "full_name", "customer_name", "display_name"):
        if key in lower_row and lower_row[key].strip():
            result["name"] = lower_row[key].strip()
            break

    return result


def infer_record_type_and_system(
    row: dict,
    entry: EvidenceFileEntry,
    hint: str = "",
) -> tuple[str, Optional[str]]:
    """
    Infer the semantic record_type and system_id.

    Uses (in order):
    1. ``hint`` (SQL table name)
    2. ``entry.file_path``
    3. ``entry.origin``
    4. Row-level fields (e.g. ``record_type``, ``event_type``, ``source_system``)
    5. Default: "unknown"
    """
    lower_hint = hint.lower()
    lower_path = entry.file_path.lower()
    lower_origin = entry.origin.lower()

    # 1. Table name hint (SQL)
    if lower_hint:
        for substr, rtype, sys_id in _TABLE_RULES:
            if substr in lower_hint:
                return rtype, sys_id

    # 2. File path
    for substr, rtype, sys_id in _FILE_PATH_RULES:
        if substr in lower_path:
            return rtype, sys_id

    # 3. Origin
    for substr, rtype, sys_id in _FILE_PATH_RULES:
        if substr in lower_origin:
            return rtype, sys_id

    # 4. Row-level fields
    lower_row = {k.lower(): str(v).lower() for k, v in row.items()}
    for field in ("record_type", "event_type", "data_category"):
        if field in lower_row:
            val = lower_row[field]
            for substr, rtype, sys_id in _FILE_PATH_RULES:
                if substr in val:
                    return rtype, sys_id
    if "source_system" in lower_row:
        src = lower_row["source_system"]
        for substr, rtype, sys_id in _FILE_PATH_RULES:
            if substr in src:
                return rtype, sys_id

    return "unknown", None


def safe_parse_datetime(value: str) -> Optional[datetime]:
    """
    Parse an ISO-8601 datetime string without raising.

    Returns None on failure.  Handles common variants:
    - 2026-10-01T12:00:00Z
    - 2026-10-01 12:00:00
    - 2026-10-01T12:00:00+05:30
    """
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    # Normalise space separator to T
    value = re.sub(r'^(\d{4}-\d{2}-\d{2})\s+(\d{2})', r'\1T\2', value)
    # Try multiple formats
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S.%f",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    # Try datetime.fromisoformat (Python 3.7+)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    logger.debug("Cannot parse datetime: %r", value)
    return None
