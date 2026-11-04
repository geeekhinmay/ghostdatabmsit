"""
JSON / JSONL evidence parser.

Handles evidence/records/*.json bundles (snapshot bundles, analytics reports,
connector configs, export manifests, security audit ledgers, service-resource
exports) and JSONL files.

Owned by: Member 2 — Chinmay Motagi
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from code.models.enums import EvidenceFormat
from code.models.schemas import EvidenceFileEntry, EvidenceRecord
from code.parsers.common import (
    build_base_record,
    extract_identifiers,
    infer_record_type_and_system,
    safe_parse_datetime,
)

logger = logging.getLogger(__name__)


def parse_json_evidence(
    abs_path: Path,
    entry: EvidenceFileEntry,
    fmt: EvidenceFormat,
) -> list[EvidenceRecord]:
    """
    Parse a JSON or JSONL evidence file.

    - For JSON: the top-level value may be a list of objects or a single
      object.  If it is a dict with a recognisable container key (e.g.
      ``"accounts"``, ``"records"``, ``"customers"``), the nested list is
      extracted.  Otherwise the whole dict is treated as one record.
    - For JSONL: each newline-delimited JSON object becomes one record.
    """
    records: list[EvidenceRecord] = []

    try:
        raw_text = abs_path.read_text(encoding="utf-8-sig")
    except Exception as exc:  # noqa: BLE001
        logger.error("Cannot read JSON file %s: %s", abs_path, exc)
        return records

    if fmt == EvidenceFormat.JSONL:
        items: list[Any] = []
        for i, line in enumerate(raw_text.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.warning("JSONL line %d in %s invalid: %s", i, entry.file_id, exc)
    else:
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            logger.error("JSON parse error in %s: %s", entry.file_id, exc)
            return records

        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, dict):
            # Unwrap known container keys; fall back to single-object treatment
            items = _unwrap_dict(parsed)
        else:
            logger.warning("Unexpected JSON root type in %s: %s", entry.file_id, type(parsed))
            return records

    for i, item in enumerate(items):
        if not isinstance(item, dict):
            logger.debug("JSON item %d in %s is not a dict — skipping", i, entry.file_id)
            continue
        try:
            flat = _flatten(item)
            base = build_base_record(entry, fmt)
            ids = extract_identifiers(flat)
            rtype, sys_id = infer_record_type_and_system(flat, entry)
            resource_id = _extract_resource_id(flat, item)
            ts = _extract_timestamp(flat)

            rec = EvidenceRecord(
                **base,
                record_type=rtype,
                system_id=sys_id,
                resource_id=resource_id,
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
            logger.warning("JSON item %d in %s skipped: %s", i, entry.file_id, exc)

    return records


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Known top-level container keys in snapshot bundles
_CONTAINER_KEYS = [
    "accounts", "records", "customers", "users", "entries",
    "connectors", "data_flows", "exports", "analytics",
    "audit_records", "security_records", "marketing_profiles",
    "search_indexes", "support_records", "backup_records",
    "tombstones", "resources", "items", "results",
]


def _unwrap_dict(d: dict) -> list[dict]:
    """
    If the dict has one recognisable container key, return its value.
    Otherwise wrap the dict as a single-element list.
    """
    for key in _CONTAINER_KEYS:
        if key in d and isinstance(d[key], list):
            return d[key]
    # Return dict itself as single record
    return [d]


def _flatten(obj: dict, prefix: str = "", sep: str = ".") -> dict:
    """
    Shallow-flatten a nested dict one level deep so identity fields in
    nested sub-objects are reachable by extract_identifiers.
    """
    out: dict = {}
    for k, v in obj.items():
        full_key = f"{prefix}{sep}{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten(v, full_key, sep))
        else:
            out[full_key] = str(v) if v is not None else ""
    return out


_RESOURCE_ID_KEYS = [
    "id", "resource_id", "account_id", "search_id", "support_id",
    "export_id", "analytics_id", "backup_id", "data_flow_id",
    "audit_record_id", "tombstone_id", "connector_id",
    "marketing_id", "record_id",
]

_TIMESTAMP_KEYS = [
    "created_at", "updated_at", "event_time", "timestamp",
    "captured_at", "deleted_at", "exported_at", "retained_at",
    "snapshot_at", "audit_time",
]


def _extract_resource_id(flat: dict, original: dict) -> str | None:
    for key in _RESOURCE_ID_KEYS:
        if key in flat and flat[key]:
            return str(flat[key]).strip()
    # Fallback: look for any *_id key
    for k, v in flat.items():
        if k.endswith("_id") and v:
            return str(v).strip()
    return None


def _extract_timestamp(flat: dict):
    for key in _TIMESTAMP_KEYS:
        if key in flat and flat[key]:
            return safe_parse_datetime(str(flat[key]))
    return None
