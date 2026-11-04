"""Shared Pydantic data schemas for the Ghost Data deletion audit system.

All four developers import and use these models to ensure seamless
module integration and contract compliance.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from code.models.enums import (
    ALLOWED_OPERATION_STATES,
    PHASE_ALLOWED_OPERATIONS,
    DataCategory,
    DeletionStatus,
    EvidenceFormat,
    FindingOperation,
    Phase,
    RemediationOperation,
    ReportedStatus,
    RequiredAction,
    State,
    StepOperation,
    StepPhase,
    StepState,
    VerificationOperation,
)


# ---------------------------------------------------------------------------
# Dataset CSV row models (Used by code.ingestion & all modules)
# ---------------------------------------------------------------------------


class DeletionRequest(BaseModel):
    """One row from dataset/deletion_requests.csv or sample_deletion_requests.csv."""
    model_config = ConfigDict(extra="ignore")

    case_id: str
    email: str
    requested_at: datetime | str
    reported_status: ReportedStatus
    reported_at: datetime | str
    audit_at: datetime | str
    request_text: str


class UserIdentity(BaseModel):
    """One row from dataset/user_identities.csv (current snapshot)."""
    model_config = ConfigDict(extra="ignore")

    user_id: str
    name: str
    email: str
    phone: str
    email_hash: str
    updated_at: datetime | str


class UserAuditEntry(BaseModel):
    """One row from dataset/user_audit_log.csv."""
    model_config = ConfigDict(extra="ignore")

    audit_id: str
    user_id: str
    event_time: datetime | str
    field_name: str
    old_value: str
    new_value: str

    @property
    def field_changed(self) -> str:
        return self.field_name

    @property
    def changed_at(self) -> datetime | str:
        return self.event_time


# Alias for Member 1 compatibility
UserAuditRecord = UserAuditEntry


class SystemActivity(BaseModel):
    """One row from dataset/system_activity.csv."""
    model_config = ConfigDict(extra="ignore")

    activity_id: str
    event_time: datetime | str
    event_type: str
    source_system: str
    target_system: str = ""
    resource_id: str
    reported_result: str
    details: str = ""

    @property
    def system_id(self) -> str:
        return self.source_system

    @property
    def action(self) -> str:
        return self.event_type

    @property
    def status(self) -> str:
        return self.reported_result

    @property
    def timestamp(self) -> datetime | str:
        return self.event_time


# Alias for Member 1 compatibility
SystemActivityRecord = SystemActivity


class DeletionRule(BaseModel):
    """One row from dataset/deletion_rules.csv."""
    model_config = ConfigDict(extra="ignore")

    rule_id: str
    data_category: DataCategory | str
    condition: str
    required_action: RequiredAction | str


class EvidenceFileEntry(BaseModel):
    """One row from dataset/evidence_files.csv (the manifest)."""
    model_config = ConfigDict(extra="ignore")

    file_id: str
    file_path: str  # relative to dataset/
    origin: str
    captured_at: datetime


# Alias for Member 1 compatibility
EvidenceFileManifest = EvidenceFileEntry


# ---------------------------------------------------------------------------
# Parsed evidence record (produced by Member 2's parsers)
# ---------------------------------------------------------------------------


class EvidenceRecord(BaseModel):
    """
    Normalised evidence extracted from one evidence file.

    Produced by: Member 2 (parse_all_evidence)
    Consumed by: Members 3 and 4
    """
    model_config = ConfigDict(extra="ignore")

    # Source identity
    file_id: str = Field(description="evidence_files.csv file_id")
    file_path: str = Field(description="Relative path within dataset/")
    file_format: EvidenceFormat = Field(default=EvidenceFormat.UNKNOWN)
    origin: str = Field(default="", description="origin field from evidence_files.csv")
    captured_at: datetime = Field(description="Snapshot time of the evidence file")

    # Content
    record_type: str = Field(
        default="unknown",
        description=(
            "Semantic category: account, search_index, support_message, "
            "analytics_profile, export, marketing, email_log, security_audit, "
            "legal_hold, backup, connector, tombstone, activity_event, unknown"
        ),
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

    # Member 1 compatibility
    content: Any = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def file_type(self) -> str:
        return self.file_format.value if isinstance(self.file_format, EvidenceFormat) else str(self.file_format)


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
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    deletion_requests: List[DeletionRequest] = Field(default_factory=list)
    sample_requests: List[DeletionRequest] = Field(default_factory=list)
    user_identities: List[UserIdentity] = Field(default_factory=list)
    user_audit_log: List[UserAuditEntry] = Field(default_factory=list)
    system_activity: List[SystemActivity] = Field(default_factory=list)
    deletion_rules: List[DeletionRule] = Field(default_factory=list)
    evidence_manifest: List[EvidenceFileEntry] = Field(default_factory=list)

    # Quick-lookup indexes built at load time
    requests_by_case_id: Dict[str, DeletionRequest] = Field(default_factory=dict)
    identities_by_user_id: Dict[str, UserIdentity] = Field(default_factory=dict)
    identities_by_email: Dict[str, UserIdentity] = Field(default_factory=dict)
    rules_by_category: Dict[str, DeletionRule] = Field(default_factory=dict)
    manifest_by_file_id: Dict[str, EvidenceFileEntry] = Field(default_factory=dict)
    activity_by_id: Dict[str, SystemActivity] = Field(default_factory=dict)
    audit_by_id: Dict[str, UserAuditEntry] = Field(default_factory=dict)

    # Member 1 compatibility properties & fields
    evidence_records: Dict[str, EvidenceRecord] = Field(default_factory=dict)

    @property
    def requests(self) -> Dict[str, DeletionRequest]:
        return self.requests_by_case_id

    @property
    def rules(self) -> List[DeletionRule]:
        return self.deletion_rules

    @property
    def manifest(self) -> Dict[str, EvidenceFileEntry]:
        return self.manifest_by_file_id

    @property
    def activities(self) -> List[SystemActivity]:
        return self.system_activity

    @property
    def audit_logs_by_user_id(self) -> Dict[str, List[UserAuditEntry]]:
        res: Dict[str, List[UserAuditEntry]] = {}
        for entry in self.user_audit_log:
            res.setdefault(entry.user_id, []).append(entry)
        return res

    @property
    def audit_logs_by_email(self) -> Dict[str, List[UserAuditEntry]]:
        res: Dict[str, List[UserAuditEntry]] = {}
        for entry in self.user_audit_log:
            if entry.field_name == "email":
                if entry.old_value:
                    res.setdefault(entry.old_value.lower(), []).append(entry)
                if entry.new_value:
                    res.setdefault(entry.new_value.lower(), []).append(entry)
        return res


# ---------------------------------------------------------------------------
# Step and output models (used by output module & orchestrator)
# ---------------------------------------------------------------------------


class AuditStep(BaseModel):
    """Single step in the steps_json output array."""
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    step_no: int = Field(..., ge=1, description="1-based consecutive step number")
    phase: StepPhase = Field(..., description="Workflow phase: FINDING, REMEDIATION, or VERIFICATION")
    system_id: str = Field(..., min_length=1, description="Identifier of the system or service")
    resource_id: str = Field(..., min_length=1, description="Identifier of the specific resource or record")
    operation: StepOperation | str = Field(..., description="Action or check being performed")
    state: StepState | str = Field(..., description="Expected or resulting state")
    evidence_id: str = Field(default="", description="Cites participant-visible evidence; empty for proposed actions")

    @field_validator("operation")
    @classmethod
    def validate_operation_known(cls, v: Any) -> str:
        op_val = v.value if hasattr(v, "value") else str(v)
        if op_val not in ALLOWED_OPERATION_STATES:
            raise ValueError(f"Unknown operation '{op_val}'. Must be one of {list(ALLOWED_OPERATION_STATES.keys())}")
        return op_val

    @model_validator(mode="after")
    def validate_phase_operation_state_evidence(self) -> AuditStep:
        op_str = self.operation.value if hasattr(self.operation, "value") else str(self.operation)
        phase_str = self.phase.value if hasattr(self.phase, "value") else str(self.phase)
        state_str = self.state.value if hasattr(self.state, "value") else str(self.state)

        # Check operation matches phase
        allowed_ops = PHASE_ALLOWED_OPERATIONS.get(self.phase, set())
        if op_str not in allowed_ops:
            raise ValueError(f"Operation '{op_str}' is not allowed in phase '{phase_str}'")

        # Check state matches operation
        expected_state = ALLOWED_OPERATION_STATES.get(op_str)
        if expected_state and state_str != expected_state.value:
            raise ValueError(
                f"State '{state_str}' does not match operation '{op_str}'. Expected '{expected_state.value}'"
            )

        # In REMEDIATION, evidence_id must be empty string
        if self.phase == StepPhase.REMEDIATION and self.evidence_id != "":
            raise ValueError(f"Remediation step {self.step_no} must have empty evidence_id (''), got '{self.evidence_id}'")

        return self


# Alias for Step
Step = AuditStep


class OutputRow(BaseModel):
    """Single output row for output.csv."""
    model_config = ConfigDict(extra="ignore")

    case_id: str
    deletion_status: DeletionStatus
    steps_json: List[Step] = Field(default_factory=list)

    @property
    def steps(self) -> List[Step]:
        return self.steps_json

    @model_validator(mode="after")
    def validate_row_contract(self) -> OutputRow:
        if self.deletion_status == DeletionStatus.NOT_APPLICABLE and len(self.steps_json) > 0:
            raise ValueError(f"Case {self.case_id} is NOT_APPLICABLE so steps_json must be empty, got {len(self.steps_json)} steps")
        return self


# Alias for CaseResult
CaseResult = OutputRow


# ---------------------------------------------------------------------------
# Investigation & Policy models (Consumed by Orchestrator & Members 3 and 4)
# ---------------------------------------------------------------------------


class IdentityResolution(BaseModel):
    """Resolved current and historical identity profile produced by Member 3."""
    model_config = ConfigDict(extra="ignore")

    case_id: str
    user_id: Optional[str] = None
    current_name: Optional[str] = None
    current_email: Optional[str] = None
    current_phone: Optional[str] = None
    current_hash: Optional[str] = None
    all_emails: set[str] = Field(default_factory=set)
    all_names: set[str] = Field(default_factory=set)
    all_phones: set[str] = Field(default_factory=set)
    all_hashes: set[str] = Field(default_factory=set)
    audit_history: List[UserAuditEntry] = Field(default_factory=list)


class InvestigationFinding(BaseModel):
    """Single finding identified during case investigation."""
    model_config = ConfigDict(extra="ignore")

    system_id: str
    resource_id: str
    operation: StepOperation | str
    state: StepState | str
    evidence_id: str
    category: Optional[str] = None
    details: str = ""


class InvestigationResult(BaseModel):
    """Case investigation output produced by Member 3."""
    model_config = ConfigDict(extra="ignore")

    case_id: str
    is_deletion_request: bool = True
    identity: IdentityResolution
    findings: List[InvestigationFinding] = Field(default_factory=list)
    retained_records: List[Dict[str, Any]] = Field(default_factory=list)
    active_flows: List[Dict[str, Any]] = Field(default_factory=list)
    restore_risks: List[Dict[str, Any]] = Field(default_factory=list)
    audit_cutoff: str = ""


class PolicyDecision(BaseModel):
    """Policy decision and planned actions produced by Member 4."""
    model_config = ConfigDict(extra="ignore")

    case_id: str
    deletion_status: DeletionStatus
    remediation_steps: List[Step] = Field(default_factory=list)
    verification_steps: List[Step] = Field(default_factory=list)
    applied_rules: List[str] = Field(default_factory=list)
    rationale: str = ""
