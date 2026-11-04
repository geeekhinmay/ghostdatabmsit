"""
Domain models for policy decisions and evaluation results.

Owned by: Member 4 (Hrushikesh)
Module: code/policy/models.py
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from code.models.enums import DeletionStatus, RequiredAction
from code.models.schemas import AuditStep


class PolicyDecision(BaseModel):
    """
    Result of evaluating deletion policy on a request and its investigated resources.

    Consumed by:
    - Member 4: build_remediation_plan, build_verification_steps
    - Member 1: orchestrator, output generation
    """

    case_id: str = Field(description="Unique identifier for the case")
    is_deletion_request: bool = Field(
        default=True,
        description="Whether the request text actually authorises personal data deletion",
    )
    deletion_status: DeletionStatus = Field(
        description="COMPLETE, INCOMPLETE, or NOT_APPLICABLE",
    )
    non_deletion_reason: Optional[str] = Field(
        default=None,
        description="Explanation if the request was classified as NOT_APPLICABLE",
    )
    findings: List[AuditStep] = Field(
        default_factory=list,
        description="Ordered list of findings (REPORT_*) for incomplete cases",
    )
    remediation_items: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Intermediate structured representation of needed remediation actions",
    )
    verification_items: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Intermediate structured representation of required verification checks",
    )
    treatment_by_resource: Dict[str, RequiredAction] = Field(
        default_factory=dict,
        description="Mapping from resource_id to RequiredAction (DELETE, REDACT, ANONYMIZE, RETAIN)",
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional diagnostic or audit metadata",
    )

    model_config = {"arbitrary_types_allowed": True}
