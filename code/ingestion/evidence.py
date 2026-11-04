"""
Evidence dispatcher — iterates the manifest, dispatches each file to the
appropriate format-specific parser, and returns a flat list of EvidenceRecords.

Owned by: Member 2 — Chinmay Motagi
Public function: parse_all_evidence(dataset_dir, manifest) -> list[EvidenceRecord]
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Union

from code.models.enums import EvidenceFormat
from code.models.schemas import EvidenceFileEntry, EvidenceRecord
from code.parsers.csv_parser import parse_csv_evidence
from code.parsers.json_parser import parse_json_evidence
from code.parsers.sql_parser import parse_sql_evidence
from code.parsers.log_parser import parse_log_evidence
from code.parsers.pdf_parser import parse_pdf_evidence
from code.parsers.image_parser import parse_image_evidence

logger = logging.getLogger(__name__)

# Map file extensions to EvidenceFormat and parser callables
_EXT_FORMAT: dict[str, EvidenceFormat] = {
    ".csv": EvidenceFormat.CSV,
    ".tsv": EvidenceFormat.TSV,
    ".json": EvidenceFormat.JSON,
    ".jsonl": EvidenceFormat.JSONL,
    ".sql": EvidenceFormat.SQL,
    ".log": EvidenceFormat.LOG,
    ".txt": EvidenceFormat.TXT,
    ".pdf": EvidenceFormat.PDF,
    ".png": EvidenceFormat.PNG,
    ".jpg": EvidenceFormat.JPG,
    ".jpeg": EvidenceFormat.JPG,
}


def _detect_format(file_path: str) -> EvidenceFormat:
    """Return the EvidenceFormat for a given file path based on its extension."""
    ext = Path(file_path).suffix.lower()
    return _EXT_FORMAT.get(ext, EvidenceFormat.UNKNOWN)


def _parse_file(
    abs_path: Path,
    entry: EvidenceFileEntry,
    fmt: EvidenceFormat,
) -> list[EvidenceRecord]:
    """
    Dispatch a single evidence file to its format-specific parser.

    Returns an empty list if the file is missing or if parsing fails
    entirely; partial results are still returned on per-row errors.
    """
    if not abs_path.exists():
        logger.warning("Evidence file missing: %s (file_id=%s)", abs_path, entry.file_id)
        return []

    try:
        if fmt in (EvidenceFormat.CSV, EvidenceFormat.TSV):
            return parse_csv_evidence(abs_path, entry, fmt)
        elif fmt in (EvidenceFormat.JSON, EvidenceFormat.JSONL):
            return parse_json_evidence(abs_path, entry, fmt)
        elif fmt == EvidenceFormat.SQL:
            return parse_sql_evidence(abs_path, entry)
        elif fmt in (EvidenceFormat.LOG, EvidenceFormat.TXT):
            return parse_log_evidence(abs_path, entry, fmt)
        elif fmt == EvidenceFormat.PDF:
            return parse_pdf_evidence(abs_path, entry)
        elif fmt in (EvidenceFormat.PNG, EvidenceFormat.JPG):
            return parse_image_evidence(abs_path, entry, fmt)
        else:
            logger.warning(
                "Unknown format for %s (file_id=%s) — returning empty",
                abs_path.name,
                entry.file_id,
            )
            return []
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to parse %s (file_id=%s): %s", abs_path, entry.file_id, exc
        )
        return []


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def parse_all_evidence(
    dataset_dir: Union[str, Path],
    manifest: list[EvidenceFileEntry],
) -> list[EvidenceRecord]:
    """
    Parse every evidence file listed in *manifest* and return a flat list of
    normalised :class:`~code.models.schemas.EvidenceRecord` objects.

    Parameters
    ----------
    dataset_dir:
        Path to the ``dataset/`` directory.  File paths from the manifest are
        resolved relative to this directory.
    manifest:
        The list of :class:`~code.models.schemas.EvidenceFileEntry` objects
        produced by :func:`~code.ingestion.loader.load_dataset`.

    Returns
    -------
    list[EvidenceRecord]
        One record per meaningful item extracted from the evidence files.
        Multiple records may be produced from a single file (e.g. one per
        SQL row or JSON array element).

    Notes
    -----
    - Evidence is **not** automatically attributed to a user or case here.
      That mapping happens in the identity and investigation modules.
    - Files captured after a case's ``audit_at`` must be filtered out by the
      caller (investigation module) — the ingestion layer preserves all
      ``captured_at`` values so callers can apply their own time window.
    - Missing files and parse errors are logged but do not raise exceptions.
    """
    dataset_dir = Path(dataset_dir)
    all_records: list[EvidenceRecord] = []

    for entry in manifest:
        abs_path = dataset_dir / entry.file_path
        fmt = _detect_format(entry.file_path)
        logger.debug(
            "Parsing %s (file_id=%s, format=%s)", entry.file_path, entry.file_id, fmt
        )
        records = _parse_file(abs_path, entry, fmt)
        all_records.extend(records)

    logger.info(
        "parse_all_evidence: %d manifest entries -> %d evidence records",
        len(manifest),
        len(all_records),
    )
    return all_records
