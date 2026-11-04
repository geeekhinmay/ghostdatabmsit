# code/ingestion/__init__.py
"""
Data ingestion package.

Owned by: Member 2 — Chinmay Motagi

Public API:
    load_dataset(dataset_dir: str | Path) -> DatasetBundle
    parse_all_evidence(dataset_dir: str | Path, manifest: list[EvidenceFileEntry]) -> list[EvidenceRecord]
"""

from code.ingestion.loader import load_dataset
from code.ingestion.evidence import parse_all_evidence

__all__ = ["load_dataset", "parse_all_evidence"]
