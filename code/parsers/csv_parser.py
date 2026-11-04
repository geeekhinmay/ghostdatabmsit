"""
CSV / TSV evidence parser.

Handles:
- evidence/records/*.json (CSV-like records bundles)
- Any .csv or .tsv evidence file

Owned by: Member 2 — Chinmay Motagi
"""

from __future__ import annotations

import csv
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


def parse_csv_evidence(
    abs_path: Path,
    entry: EvidenceFileEntry,
    fmt: EvidenceFormat,
) -> list[EvidenceRecord]:
    """
    Parse a CSV or TSV evidence file.

    Each data row becomes one EvidenceRecord.  Columns are mapped to identity
    fields where recognised; all columns are preserved in ``raw_fields``.
    """
    delimiter = "\t" if fmt == EvidenceFormat.TSV else ","
    records: list[EvidenceRecord] = []

    try:
        with abs_path.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh, delimiter=delimiter)
            for i, row in enumerate(reader):
                try:
                    base = build_base_record(entry, fmt)
                    ids = extract_identifiers(row)
                    rtype, sys_id = infer_record_type_and_system(row, entry)
                    resource_id = _extract_resource_id(row)
                    ts = _extract_timestamp(row)

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
                        raw_fields=dict(row),
                    )
                    records.append(rec)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "CSV row %d in %s skipped: %s", i, entry.file_id, exc
                    )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to open CSV %s: %s", abs_path, exc)

    return records


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RESOURCE_ID_KEYS = [
    "resource_id", "account_id", "search_id", "support_id",
    "export_id", "analytics_id", "backup_id", "data_flow_id",
    "audit_record_id", "tombstone_id", "connector_id", "marketing_id",
]

_TIMESTAMP_KEYS = [
    "created_at", "updated_at", "event_time", "timestamp",
    "captured_at", "deleted_at", "exported_at", "retained_at",
]


def _extract_resource_id(row: dict) -> str | None:
    for key in _RESOURCE_ID_KEYS:
        if key in row and row[key]:
            return row[key].strip()
    # Try to find any column whose name ends with _id
    for k, v in row.items():
        if k.endswith("_id") and v:
            return v.strip()
    return None


def _extract_timestamp(row: dict):
    for key in _TIMESTAMP_KEYS:
        if key in row and row[key]:
            return safe_parse_datetime(row[key])
    return None
