"""Shared Pydantic data schemas for the Ghost Data deletion audit system.

All four developers must import and use these models to ensure seamless
module integration and contract compliance.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from code.models.enums import (
    ALLOWED_OPERATION_STATES,
    PHASE_ALLOWED_OPERATIONS,
    DataCategory,
    DeletionStatus,
    Phase,
    ReportedStatus,
    RequiredAction,
    State,
)


class Step(BaseModel):
    """Single step in the steps_json output array."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    step_no: int = Field(..., ge=1, description="1-based consecutive step number")
    phase: Phase = Field(..., description="Workflow phase: FINDING, REMEDIATION, or VERIFICATION")
    system_id: str = Field(..., min_length=1, description="Identifier of the system or service")
    resource_id: str = Field(..., min_length=1, description="Identifier of the specific resource or record")
    operation: str = Field(..., description="Action or check being performed")
    state: State = Field(..., description="Expected or resulting state")
    evidence_id: str = Field(default="", description="Cites participant-visible evidence; empty for proposed actions")

    @field_validator("operation")
    @classmethod
    def validate_operation_known(cls, v: str) -> str:
        if v not in ALLOWED_OPERATION_STATES:
            raise ValueError(f"Unknown operation '{v}'. Must be one of {list(ALLOWED_OPERATION_STATES.keys())}")
        return v

    @model_validator(mode="after")
    def validate_phase_operation_state_evidence(self) -> Step:
        # Check operation matches phase
        allowed_ops = PHASE_ALLOWED_OPERATIONS.get(self.phase, set())
        if self.operation not in allowed_ops:
            raise ValueError(f"Operation '{self.operation}' is not allowed in phase '{self.phase.value}'")

        # Check state matches operation
        expected_state = ALLOWED_OPERATION_STATES.get(self.operation)
        if expected_state and self.state != expected_state:
            raise ValueError(
                f"State '{self.state.value}' does not match operation '{self.operation}'. Expected '{expected_state.value}'"
            )

        # In REMEDIATION, evidence_id must be empty string
        if self.phase == Phase.REMEDIATION and self.evidence_id != "":
            raise ValueError(f"Remediation step {self.step_no} must have empty evidence_id (''), got '{self.evidence_id}'")

        return self


class DeletionRequest(BaseModel):
    """Row from deletion_requests.csv or sample_deletion_requests.csv."""
    model_config = ConfigDict(extra="ignore")

    case_id: str
    email: str
    requested_at: str
    reported_status: ReportedStatus
    reported_at: str
    audit_at: str
    request_text: str


class UserIdentity(BaseModel):
    """Current user identity snapshot from user_identities.csv."""
    model_config = ConfigDict(extra="ignore")

    user_id: str
    name: str
    email: str
    phone: str
    email_hash: str
    updated_at: str


class UserAuditRecord(BaseModel):
    """Historical user identity modification from user_audit_log.csv."""
    model_config = ConfigDict(extra="ignore")

    audit_id: str
    user_id: str
    event_time: str
    field_name: str
    old_value: str
    new_value: str

    @property
    def field_changed(self) -> str:
        return self.field_name

    @property
    def changed_at(self) -> str:
        return self.event_time


class SystemActivityRecord(BaseModel):
    """Operational event from system_activity.csv."""
    model_config = ConfigDict(extra="ignore")

    activity_id: str
    event_time: str
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
    def timestamp(self) -> str:
        return self.event_time


class DeletionRule(BaseModel):
    """Policy rule from deletion_rules.csv."""
    model_config = ConfigDict(extra="ignore")

    rule_id: str
    data_category: DataCategory | str
    condition: str
    required_action: RequiredAction | str


class EvidenceFileManifest(BaseModel):
    """Evidence manifest row from evidence_files.csv."""
    model_config = ConfigDict(extra="ignore")

    file_id: str
    file_path: str
    origin: str
    captured_at: str


class EvidenceRecord(BaseModel):
    """Normalized evidence file content parsed by Member 2."""
    model_config = ConfigDict(extra="ignore")

    file_id: str
    file_path: str
    file_type: str  # sql, log, json, image, document, text
    origin: str
    captured_at: str
    content: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatasetBundle(BaseModel):
    """Complete dataset bundle loaded and indexed by Member 2."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    requests: dict[str, DeletionRequest] = Field(default_factory=dict)
    identities_by_user_id: dict[str, UserIdentity] = Field(default_factory=dict)
    identities_by_email: dict[str, UserIdentity] = Field(default_factory=dict)
    audit_logs_by_user_id: dict[str, list[UserAuditRecord]] = Field(default_factory=dict)
    audit_logs_by_email: dict[str, list[UserAuditRecord]] = Field(default_factory=dict)
    activities: list[SystemActivityRecord] = Field(default_factory=list)
    rules: list[DeletionRule] = Field(default_factory=list)
    manifest: dict[str, EvidenceFileManifest] = Field(default_factory=dict)
    evidence_records: dict[str, EvidenceRecord] = Field(default_factory=dict)


class IdentityResolution(BaseModel):
    """Resolved current and historical identity profile produced by Member 3."""
    model_config = ConfigDict(extra="ignore")

    case_id: str
    user_id: str | None = None
    current_name: str | None = None
    current_email: str | None = None
    current_phone: str | None = None
    current_hash: str | None = None
    all_emails: set[str] = Field(default_factory=set)
    all_names: set[str] = Field(default_factory=set)
    all_phones: set[str] = Field(default_factory=set)
    all_hashes: set[str] = Field(default_factory=set)
    audit_history: list[UserAuditRecord] = Field(default_factory=list)


class InvestigationFinding(BaseModel):
    """Single finding identified during case investigation."""
    model_config = ConfigDict(extra="ignore")

    system_id: str
    resource_id: str
    operation: str
    state: State
    evidence_id: str
    category: str | None = None
    details: str = ""


class InvestigationResult(BaseModel):
    """Case investigation output produced by Member 3."""
    model_config = ConfigDict(extra="ignore")

    case_id: str
    is_deletion_request: bool = True
    identity: IdentityResolution
    findings: list[InvestigationFinding] = Field(default_factory=list)
    retained_records: list[dict[str, Any]] = Field(default_factory=list)
    active_flows: list[dict[str, Any]] = Field(default_factory=list)
    restore_risks: list[dict[str, Any]] = Field(default_factory=list)
    audit_cutoff: str = ""


class PolicyDecision(BaseModel):
    """Policy decision and planned actions produced by Member 4."""
    model_config = ConfigDict(extra="ignore")

    case_id: str
    deletion_status: DeletionStatus
    remediation_steps: list[Step] = Field(default_factory=list)
    verification_steps: list[Step] = Field(default_factory=list)
    applied_rules: list[str] = Field(default_factory=list)
    rationale: str = ""


class OutputRow(BaseModel):
    """Single output row for output.csv."""
    model_config = ConfigDict(extra="forbid")

    case_id: str
    deletion_status: DeletionStatus
    steps_json: list[Step] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_row_contract(self) -> OutputRow:
        if self.deletion_status == DeletionStatus.NOT_APPLICABLE and len(self.steps_json) > 0:
            raise ValueError(f"Case {self.case_id} is NOT_APPLICABLE so steps_json must be empty, got {len(self.steps_json)} steps")
        return self
