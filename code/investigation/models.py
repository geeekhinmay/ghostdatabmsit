"""
Domain models for investigation findings and discovered resources.

Owned by: Member 3 (Chirag Gowda)
Module: code/investigation/models.py
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from code.models.enums import StepState


class InvestigatedResource(BaseModel):
    """
    A single customer record discovered in evidence across databases, replicas,
    search indexes, customer support, analytics, exports, or tombstones.
    """

    system_id: str = Field(description="Target system (e.g. 'account_service', 'search_service')")
    resource_id: str = Field(description="Unique resource identifier (e.g. 'account_001', 'search_052')")
    state: Union[StepState, str] = Field(
        default=StepState.PRESENT,
        description="Observed state in evidence: PRESENT, ABSENT, REDACTED, or ANONYMIZED",
    )
    evidence_id: str = Field(
        default="",
        description="Evidence file ID proving the finding or verification state",
    )
    data_category: Optional[str] = Field(
        default=None,
        description="Explicit policy category from deletion_rules.csv (e.g. 'SUPPORT_ATTACHMENT')",
    )
    has_exposed_pii: Optional[bool] = Field(
        default=None,
        description="Whether personally identifiable information remains exposed",
    )
    is_attributable: Optional[bool] = Field(
        default=None,
        description="Whether analytics profile remains attributable to the user",
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Diagnostic details from parsing and correlation",
    )

    model_config = {"arbitrary_types_allowed": True}


class InvestigatedDataFlow(BaseModel):
    """
    An investigated sync connector or data flow pipeline.
    """

    system_id: str = Field(
        default="integration_service",
        description="Target system for data flow",
    )
    resource_id: str = Field(description="Connector or pipeline resource ID (e.g. 'data_flow_9522')")
    state: Union[StepState, str] = Field(
        default=StepState.ACTIVE,
        description="Observed state: ACTIVE or DISABLED",
    )
    is_active: bool = Field(
        default=True,
        description="Whether the data flow is active/enabled",
    )
    evidence_id: str = Field(
        default="",
        description="Evidence file ID where the flow was observed",
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Diagnostic details",
    )

    model_config = {"arbitrary_types_allowed": True}


class InvestigatedRestoreRisk(BaseModel):
    """
    An investigated backup archive or restore path.
    """

    system_id: str = Field(
        default="backup_service",
        description="Target system for backup",
    )
    resource_id: str = Field(description="Backup archive resource ID (e.g. 'backup_4978')")
    state: Union[StepState, str] = Field(
        default=StepState.ACTIVE,
        description="Observed state: ACTIVE or BLOCKED",
    )
    can_restore: bool = Field(
        default=True,
        description="Whether the backup archive can be restored",
    )
    is_blocked: bool = Field(
        default=False,
        description="Whether restore access is confirmed blocked",
    )
    evidence_id: str = Field(
        default="",
        description="Evidence file ID where the risk was observed",
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Diagnostic details",
    )

    model_config = {"arbitrary_types_allowed": True}


class InvestigationResult(BaseModel):
    """
    Complete result of investigating a deletion request across all evidence files
    captured up to audit_at.

    Consumed by:
    - Member 4: evaluate_policy, build_remediation_plan, build_verification_steps
    - Member 1: orchestrator, case auditing
    """

    case_id: str = Field(description="Case identifier from the deletion request")
    user_id: Optional[str] = Field(
        default=None,
        description="Resolved user_id",
    )
    audit_at: Optional[datetime] = Field(
        default=None,
        description="Audit cutoff timestamp",
    )
    primary_account: Optional[InvestigatedResource] = Field(
        default=None,
        description="Primary profile account record in account_service",
    )
    records: List[InvestigatedResource] = Field(
        default_factory=list,
        description="Discovered records in databases, indexes, support, analytics, tombstones",
    )
    data_flows: List[InvestigatedDataFlow] = Field(
        default_factory=list,
        description="Discovered active or disabled data flows in integration_service",
    )
    restore_risks: List[InvestigatedRestoreRisk] = Field(
        default_factory=list,
        description="Discovered active or blocked restore risks in backup_service",
    )
    evidence_citations: List[str] = Field(
        default_factory=list,
        description="All valid participant-visible evidence IDs cited in the investigation",
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata on evidence inspected, filtering applied, and decoy rejection",
    )

    model_config = {"arbitrary_types_allowed": True}

