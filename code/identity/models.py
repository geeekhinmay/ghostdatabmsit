"""
Domain models for identity resolution and customer profile tracking.

Owned by: Member 3 (Chirag Gowda)
Module: code/identity/models.py
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from code.models.schemas import SystemActivity, UserAuditEntry


class IdentityResolution(BaseModel):
    """
    Result of resolving a deletion request's subject against the customer
    identities dataset and historical audit logs.

    Consumed by:
    - Member 3: investigate_case
    - Member 1: orchestrator, case reporting
    - Member 4: policy evaluator
    """

    case_id: str = Field(description="Unique case identifier from the deletion request")
    user_id: Optional[str] = Field(
        default=None,
        description="Resolved canonical user_id (e.g. 'user_01', 'user_43')",
    )
    current_name: Optional[str] = Field(
        default=None,
        description="Current full name from user_identities.csv",
    )
    current_email: Optional[str] = Field(
        default=None,
        description="Current primary email address from user_identities.csv",
    )
    current_phone: Optional[str] = Field(
        default=None,
        description="Current phone number from user_identities.csv",
    )
    current_email_hash: Optional[str] = Field(
        default=None,
        description="Current SHA-256 email hash from user_identities.csv",
    )
    all_emails: List[str] = Field(
        default_factory=list,
        description="Comprehensive list of current and historical email addresses",
    )
    all_phones: List[str] = Field(
        default_factory=list,
        description="Comprehensive list of current and historical phone numbers",
    )
    all_email_hashes: List[str] = Field(
        default_factory=list,
        description="Comprehensive list of current and historical email hashes",
    )
    all_names: List[str] = Field(
        default_factory=list,
        description="Comprehensive list of known full names",
    )
    is_identified: bool = Field(
        default=False,
        description="Whether a valid user identity was matched in the system",
    )
    matched_by: str = Field(
        default="UNKNOWN",
        description="Method of identification: DIRECT_EMAIL, HISTORICAL_EMAIL, or UNKNOWN",
    )
    audit_entries: List[UserAuditEntry] = Field(
        default_factory=list,
        description="Historical identity audit log entries for this user",
    )
    associated_activities: List[SystemActivity] = Field(
        default_factory=list,
        description="System activity entries correlated with this user's deletion workflow",
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Diagnostic and audit metadata",
    )

    model_config = {"arbitrary_types_allowed": True}

