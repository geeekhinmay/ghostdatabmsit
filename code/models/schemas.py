"""
Shared Pydantic schemas for the Ghost Data Still Exists deletion-audit system.

Owned by: Member 1 (Team Lead)
Read by: All modules.

NOTE (Member 2): This file is a provisional stub so that ingestion and parsers
can be developed and tested without waiting for Member 1's PR.
Member 1's committed version is authoritative — replace this file with their
version once merged into develop.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from code.models.enums import (
    DeletionStatus,
    EvidenceFormat,
    ReportedStatus,
    RequiredAction,
    StepOperation,
    StepPhase,
    StepState,
)


# ---------------------------------------------------------------------------
# Dataset CSV row models
# ---------------------------------------------------------------------------


class DeletionRequest(BaseModel):
    """One row from dataset/deletion_requests.csv."""

    case_id: str
    email: str
    requested_at: datetime
    reported_status: ReportedStatus
    reported_at: datetime
    audit_at: datetime
    request_text: str


class UserIdentity(BaseModel):
    """One row from dataset/user_identities.csv (current snapshot)."""

    user_id: str
    name: str
    email: str
    phone: str
    email_hash: str
    updated_at: datetime


class UserAuditEntry(BaseModel):
    """One row from dataset/user_audit_log.csv."""

    audit_id: str
    user_id: str
    event_time: datetime
    field_name: str
    old_value: str
    new_value: str


class SystemActivity(BaseModel):
    """One row from dataset/system_activity.csv."""

    activity_id: str
    event_time: datetime
    event_type: str
    source_system: str
    target_system: str
    resource_id: str
    reported_result: str
    details: str


class DeletionRule(BaseModel):
    """One row from dataset/deletion_rules.csv."""

    rule_id: str
    data_category: str
    condition: str
    required_action: RequiredAction


class EvidenceFileEntry(BaseModel):
    """One row from dataset/evidence_files.csv (the manifest)."""

    file_id: str
    file_path: str  # relative to dataset/
    origin: str
    captured_at: datetime


# ---------------------------------------------------------------------------
# Parsed evidence record (produced by Member 2's parsers)
# ---------------------------------------------------------------------------


class EvidenceRecord(BaseModel):
    """
    Normalised evidence extracted from one evidence file.

    Each record represents a single meaningful data item found inside an
    evidence file — e.g. one account row, one log event, one SQL table row.

    Members 3 and 4 consume lists of these without knowing how they were
    parsed.
    """

    # Source identity
    file_id: str = Field(description="evidence_files.csv file_id")
    file_path: str = Field(description="Relative path within dataset/")
    file_format: EvidenceFormat
    origin: str = Field(description="origin field from evidence_files.csv")
    captured_at: datetime = Field(description="Snapshot time of the evidence file")

    # Content
    record_type: str = Field(
        description=(
            "Semantic category: account, search_index, support_message, "
            "analytics_profile, export, marketing, email_log, security_audit, "
            "legal_hold, backup, connector, tombstone, activity_event, unknown"
        )
    )
    system_id: Optional[str] = Field(
        default=None,
        description="System this record belongs to (e.g. account_service)",
    )
    resource_id: Optional[str] = Field(
        default=None,
        description="Unique resource ID within the system (e.g. account_042)",
    )

    # Identity linkage (extracted from content; may be None if not present)
    user_id: Optional[str] = None
    email: Optional[str] = None
    email_hash: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None

    # Timestamps from content
    record_timestamp: Optional[datetime] = None

    # Raw extracted fields (key-value pairs from the source row/entry)
    raw_fields: Dict[str, Any] = Field(default_factory=dict)

    # Parsing metadata
    parse_warnings: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Dataset bundle (output of load_dataset)
# ---------------------------------------------------------------------------


class DatasetBundle(BaseModel):
    """
    All CSV tables loaded from dataset/ as typed lists.

    Produced by: Member 2 (load_dataset)
    Consumed by: Orchestrator, identity module, investigation module,
                 policy module, all other modules.
    """

    deletion_requests: List[DeletionRequest]
    sample_requests: List[DeletionRequest]
    user_identities: List[UserIdentity]
    user_audit_log: List[UserAuditEntry]
    system_activity: List[SystemActivity]
    deletion_rules: List[DeletionRule]
    evidence_manifest: List[EvidenceFileEntry]

    # Quick-lookup indexes built at load time
    requests_by_case_id: Dict[str, DeletionRequest] = Field(default_factory=dict)
    identities_by_user_id: Dict[str, UserIdentity] = Field(default_factory=dict)
    identities_by_email: Dict[str, UserIdentity] = Field(default_factory=dict)
    rules_by_category: Dict[str, DeletionRule] = Field(default_factory=dict)
    manifest_by_file_id: Dict[str, EvidenceFileEntry] = Field(default_factory=dict)
    activity_by_id: Dict[str, SystemActivity] = Field(default_factory=dict)
    audit_by_id: Dict[str, UserAuditEntry] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


# ---------------------------------------------------------------------------
# Step and output models (used by output module — Member 1)
# ---------------------------------------------------------------------------


class AuditStep(BaseModel):
    """One entry in the steps_json array."""

    step_no: int
    phase: StepPhase
    system_id: str
    resource_id: str
    operation: StepOperation
    state: StepState
    evidence_id: str = ""


class CaseResult(BaseModel):
    """Final result row for one deletion request."""

    case_id: str
    deletion_status: DeletionStatus
    steps: List[AuditStep] = Field(default_factory=list)
# ---------------------------------------------------------------------------
# Identity & Investigation models (Member 3)
# ---------------------------------------------------------------------------

class IdentityResolution(BaseModel):
    """Result of resolving current and historical user identifiers for a case."""
    case_id: str
    user_id: Optional[str] = None
    account_ids: List[str] = Field(default_factory=list)
    emails: List[str] = Field(default_factory=list)
    phones: List[str] = Field(default_factory=list)
    email_hashes: List[str] = Field(default_factory=list)
    names: List[str] = Field(default_factory=list)
    is_resolved: bool = True


class InvestigationFinding(BaseModel):
    """An individual resource state or risk discovered during investigation."""
    system_id: str
    resource_id: str
    record_type: str
    state: str
    evidence_id: str
    details: str = ""


class InvestigationResult(BaseModel):
    """Complete evidence-backed investigation findings for a case."""
    case_id: str
    findings: List[InvestigationFinding] = Field(default_factory=list)
    active_data_flows: List[Dict[str, Any]] = Field(default_factory=list)
    restore_risks: List[Dict[str, Any]] = Field(default_factory=list)