"""
Dataset loader — loads all CSV tables from dataset/ into a DatasetBundle.

Owned by: Member 2 — Chinmay Motagi
Public function: load_dataset(dataset_dir) -> DatasetBundle
"""

from __future__ import annotations

import csv
import logging
import os
from pathlib import Path
from typing import Union

from code.models.enums import ReportedStatus, RequiredAction
from code.models.schemas import (
    DatasetBundle,
    DeletionRequest,
    DeletionRule,
    EvidenceFileEntry,
    SystemActivity,
    UserAuditEntry,
    UserIdentity,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _open_csv(path: Path) -> list[dict]:
    """
    Open a CSV file and return its rows as a list of dicts.

    Handles UTF-8 with BOM (utf-8-sig) so files exported from Windows tools
    parse cleanly.  Returns an empty list if the file is missing, logging a
    warning.
    """
    if not path.exists():
        logger.warning("CSV file not found: %s — returning empty list", path)
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return list(reader)


def _normalise_email(email: str) -> str:
    """Lowercase and strip whitespace from an email address."""
    return email.strip().lower()


def _parse_deletion_requests(rows: list[dict]) -> list[DeletionRequest]:
    records: list[DeletionRequest] = []
    for row in rows:
        try:
            records.append(
                DeletionRequest(
                    case_id=row["case_id"].strip(),
                    email=_normalise_email(row["email"]),
                    requested_at=row["requested_at"].strip(),
                    reported_status=ReportedStatus(row["reported_status"].strip()),
                    reported_at=row["reported_at"].strip(),
                    audit_at=row["audit_at"].strip(),
                    request_text=row["request_text"].strip(),
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping malformed deletion_request row %s: %s", row, exc)
    return records


def _parse_user_identities(rows: list[dict]) -> list[UserIdentity]:
    records: list[UserIdentity] = []
    for row in rows:
        try:
            records.append(
                UserIdentity(
                    user_id=row["user_id"].strip(),
                    name=row["name"].strip(),
                    email=_normalise_email(row["email"]),
                    phone=row["phone"].strip(),
                    email_hash=row["email_hash"].strip(),
                    updated_at=row["updated_at"].strip(),
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping malformed user_identity row %s: %s", row, exc)
    return records


def _parse_user_audit_log(rows: list[dict]) -> list[UserAuditEntry]:
    records: list[UserAuditEntry] = []
    for row in rows:
        try:
            records.append(
                UserAuditEntry(
                    audit_id=row["audit_id"].strip(),
                    user_id=row["user_id"].strip(),
                    event_time=row["event_time"].strip(),
                    field_name=row["field_name"].strip(),
                    old_value=row.get("old_value", "").strip(),
                    new_value=row.get("new_value", "").strip(),
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping malformed audit_log row %s: %s", row, exc)
    return records


def _parse_system_activity(rows: list[dict]) -> list[SystemActivity]:
    records: list[SystemActivity] = []
    for row in rows:
        try:
            records.append(
                SystemActivity(
                    activity_id=row["activity_id"].strip(),
                    event_time=row["event_time"].strip(),
                    event_type=row["event_type"].strip(),
                    source_system=row["source_system"].strip(),
                    target_system=row["target_system"].strip(),
                    resource_id=row["resource_id"].strip(),
                    reported_result=row["reported_result"].strip(),
                    details=row.get("details", "").strip(),
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping malformed system_activity row %s: %s", row, exc)
    return records


def _parse_deletion_rules(rows: list[dict]) -> list[DeletionRule]:
    records: list[DeletionRule] = []
    for row in rows:
        try:
            records.append(
                DeletionRule(
                    rule_id=row["rule_id"].strip(),
                    data_category=row["data_category"].strip(),
                    condition=row["condition"].strip(),
                    required_action=RequiredAction(row["required_action"].strip()),
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping malformed deletion_rule row %s: %s", row, exc)
    return records


def _parse_evidence_manifest(rows: list[dict]) -> list[EvidenceFileEntry]:
    records: list[EvidenceFileEntry] = []
    for row in rows:
        try:
            records.append(
                EvidenceFileEntry(
                    file_id=row["file_id"].strip(),
                    file_path=row["file_path"].strip(),
                    origin=row["origin"].strip(),
                    captured_at=row["captured_at"].strip(),
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping malformed evidence_manifest row %s: %s", row, exc)
    return records


def _build_indexes(bundle: DatasetBundle) -> None:
    """Populate the quick-lookup indexes on the bundle in-place."""
    bundle.requests_by_case_id = {r.case_id: r for r in bundle.deletion_requests}
    bundle.identities_by_user_id = {u.user_id: u for u in bundle.user_identities}
    bundle.identities_by_email = {u.email: u for u in bundle.user_identities}
    bundle.rules_by_category = {r.data_category: r for r in bundle.deletion_rules}
    bundle.manifest_by_file_id = {e.file_id: e for e in bundle.evidence_manifest}
    bundle.activity_by_id = {a.activity_id: a for a in bundle.system_activity}
    bundle.audit_by_id = {a.audit_id: a for a in bundle.user_audit_log}


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def load_dataset(dataset_dir: Union[str, Path]) -> DatasetBundle:
    """
    Load all participant-facing CSV tables from *dataset_dir* into a
    DatasetBundle.

    Parameters
    ----------
    dataset_dir:
        Path to the ``dataset/`` directory.  May be absolute or relative to
        the repository root.  Can be supplied as a string or a
        :class:`pathlib.Path`.

    Returns
    -------
    DatasetBundle
        All CSV tables as typed Pydantic lists with pre-built lookup indexes.

    Raises
    ------
    ValueError
        If *dataset_dir* does not exist or is not a directory.

    Notes
    -----
    - Missing files are logged as warnings and produce empty lists.
    - Malformed rows are skipped individually and logged.
    - Email addresses are normalised to lowercase for consistent lookup.
    """
    dataset_dir = Path(dataset_dir)
    if not dataset_dir.is_dir():
        raise ValueError(
            f"dataset_dir does not exist or is not a directory: {dataset_dir}"
        )

    logger.info("Loading dataset from %s", dataset_dir)

    deletion_requests = _parse_deletion_requests(
        _open_csv(dataset_dir / "deletion_requests.csv")
    )
    sample_requests = _parse_deletion_requests(
        _open_csv(dataset_dir / "sample_deletion_requests.csv")
    )
    user_identities = _parse_user_identities(
        _open_csv(dataset_dir / "user_identities.csv")
    )
    user_audit_log = _parse_user_audit_log(
        _open_csv(dataset_dir / "user_audit_log.csv")
    )
    system_activity = _parse_system_activity(
        _open_csv(dataset_dir / "system_activity.csv")
    )
    deletion_rules = _parse_deletion_rules(
        _open_csv(dataset_dir / "deletion_rules.csv")
    )
    evidence_manifest = _parse_evidence_manifest(
        _open_csv(dataset_dir / "evidence_files.csv")
    )

    logger.info(
        "Loaded: %d requests, %d identities, %d audit entries, "
        "%d activity rows, %d rules, %d evidence files",
        len(deletion_requests),
        len(user_identities),
        len(user_audit_log),
        len(system_activity),
        len(deletion_rules),
        len(evidence_manifest),
    )

    bundle = DatasetBundle(
        deletion_requests=deletion_requests,
        sample_requests=sample_requests,
        user_identities=user_identities,
        user_audit_log=user_audit_log,
        system_activity=system_activity,
        deletion_rules=deletion_rules,
        evidence_manifest=evidence_manifest,
    )
    _build_indexes(bundle)
    return bundle
