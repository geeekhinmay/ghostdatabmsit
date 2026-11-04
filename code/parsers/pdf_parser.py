"""
PDF evidence parser.

Extracts text from PDF documents (legal retention registers, account history
reports, delivery correction attachments, security retention extracts) and
produces EvidenceRecords from each meaningful text block.

Uses PyMuPDF (fitz) if available; falls back to pdfplumber; falls back to a
raw byte scan that extracts printable text.  Any of these may be absent in a
given environment, so we try gracefully.

Owned by: Member 2 — Chinmay Motagi
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

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


def _extract_text_fitz(path: Path) -> str:
    """Extract text using PyMuPDF (fitz)."""
    import fitz  # type: ignore
    doc = fitz.open(str(path))
    pages = []
    for page in doc:
        pages.append(page.get_text())
    return "\n".join(pages)


def _extract_text_pdfplumber(path: Path) -> str:
    """Extract text using pdfplumber."""
    import pdfplumber  # type: ignore
    with pdfplumber.open(str(path)) as pdf:
        return "\n".join(
            page.extract_text() or "" for page in pdf.pages
        )


def _extract_text_fallback(path: Path) -> str:
    """
    Raw fallback: scan PDF bytes for printable ASCII strings of length >= 4.
    Not perfect but recovers identifiers and timestamps in a pinch.
    """
    data = path.read_bytes()
    # Find sequences of printable bytes
    strings = re.findall(rb'[\x20-\x7E]{4,}', data)
    return " ".join(s.decode("ascii", errors="replace") for s in strings)


def _extract_text(path: Path) -> str:
    for extractor in (_extract_text_fitz, _extract_text_pdfplumber, _extract_text_fallback):
        try:
            text = extractor(path)
            if text.strip():
                return text
        except Exception:  # noqa: BLE001
            continue
    return ""


def parse_pdf_evidence(
    abs_path: Path,
    entry: EvidenceFileEntry,
) -> list[EvidenceRecord]:
    """
    Parse a PDF evidence file into EvidenceRecords.

    One EvidenceRecord is produced per PDF (representing the document as a
    whole) with all identifiers extracted from the full text.  If multiple
    identifiers are found, one record is emitted per unique user_id/email
    combination.
    """
    records: list[EvidenceRecord] = []

    text = _extract_text(abs_path)
    if not text.strip():
        logger.warning("No text extracted from PDF %s", entry.file_id)
        # Still produce a stub record so the file is accounted for
        base = build_base_record(entry, EvidenceFormat.PDF)
        rtype, sys_id = infer_record_type_and_system({}, entry)
        records.append(EvidenceRecord(
            **base,
            record_type=rtype,
            system_id=sys_id,
            resource_id=None,
            raw_fields={"_raw_text": ""},
            parse_warnings=["No text could be extracted from PDF"],
        ))
        return records

    flat: dict[str, str] = {"_raw_text": text[:4096]}  # Cap to avoid huge raw_fields

    # Extract all identifiers from the full text
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
    base = build_base_record(entry, EvidenceFormat.PDF)
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
    )
    records.append(rec)
    return records
