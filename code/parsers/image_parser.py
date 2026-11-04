"""
Image evidence parser.

Handles PNG/JPG evidence files (admin console screenshots, search index
inspector views, analytics profile views, marketing profile consoles, etc.).

Attempts OCR via pytesseract if available; falls back to producing a stub
record with metadata only.

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

_EMAIL_RE = re.compile(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}')
_EMAIL_HASH_RE = re.compile(r'\b[0-9a-f]{64}\b')
_USER_ID_RE = re.compile(r'\b(user_\d+)\b')
_RESOURCE_ID_RE = re.compile(
    r'\b(account_\d+|search_\d+|support_\d+|export_\d+|analytics_\d+|'
    r'backup_\d+|data_flow_\d+|audit_record_\d+|tombstone_\d+|'
    r'connector_\d+|marketing_\d+)\b'
)
_ISO_TS_RE = re.compile(
    r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?'
)


def _ocr_text(path: Path) -> str:
    """Attempt OCR using pytesseract."""
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore
    img = Image.open(str(path))
    return pytesseract.image_to_string(img)


def parse_image_evidence(
    abs_path: Path,
    entry: EvidenceFileEntry,
    fmt: EvidenceFormat,
) -> list[EvidenceRecord]:
    """
    Parse an image evidence file into EvidenceRecords.

    OCR is attempted; if unavailable, a stub record is produced with the
    file metadata and a warning.  The investigation module treats image
    records as business artifacts (invoices, screenshots, admin consoles).
    """
    records: list[EvidenceRecord] = []
    text = ""
    warnings: list[str] = []

    try:
        text = _ocr_text(abs_path)
    except ImportError:
        warnings.append("pytesseract or Pillow not installed — OCR skipped")
        logger.info("OCR unavailable for %s — producing metadata-only record", entry.file_id)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"OCR failed: {exc}")
        logger.warning("OCR failed for %s: %s", entry.file_id, exc)

    flat: dict[str, str] = {"_raw_text": text[:2048] if text else ""}

    if text:
        user_ids = _USER_ID_RE.findall(text)
        emails = [m.lower() for m in _EMAIL_RE.findall(text)]
        hashes = _EMAIL_HASH_RE.findall(text)
        resources = _RESOURCE_ID_RE.findall(text)
        ts_matches = _ISO_TS_RE.findall(text)

        if user_ids:
            flat["user_id"] = user_ids[0]
        if emails:
            flat["email"] = emails[0]
        if hashes:
            flat["email_hash"] = hashes[0]
        if resources:
            flat["resource_id"] = resources[0]
        if ts_matches:
            flat["event_time"] = ts_matches[0]

    ids = extract_identifiers(flat)
    base = build_base_record(entry, fmt)
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
        name=ids.get("name"),
        record_timestamp=ts,
        raw_fields=flat,
        parse_warnings=warnings,
    )
    records.append(rec)
    return records
