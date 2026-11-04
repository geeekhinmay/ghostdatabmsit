"""Shared enumeration contracts for the Ghost Data deletion audit system.

Defines the exact official allowed values for phases, operations, states,
deletion statuses, data categories, and actions.
"""

from __future__ import annotations

from enum import Enum


class DeletionStatus(str, Enum):
    """Case-level deletion status output."""
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Phase(str, Enum):
    """Audit workflow phase. Order is strictly FINDING -> REMEDIATION -> VERIFICATION."""
    FINDING = "FINDING"
    REMEDIATION = "REMEDIATION"
    VERIFICATION = "VERIFICATION"


class FindingOperation(str, Enum):
    """Allowed operations in the FINDING phase."""
    REPORT_REMAINING_RECORD = "REPORT_REMAINING_RECORD"
    REPORT_EXPOSED_PII = "REPORT_EXPOSED_PII"
    REPORT_ACTIVE_DATA_FLOW = "REPORT_ACTIVE_DATA_FLOW"
    REPORT_RESTORE_RISK = "REPORT_RESTORE_RISK"


class RemediationOperation(str, Enum):
    """Allowed operations in the REMEDIATION phase."""
    DISABLE_DATA_FLOW = "DISABLE_DATA_FLOW"
    BLOCK_RESTORE = "BLOCK_RESTORE"
    DELETE_RECORD = "DELETE_RECORD"
    REDACT_RECORD = "REDACT_RECORD"
    ANONYMIZE_RECORD = "ANONYMIZE_RECORD"


class VerificationOperation(str, Enum):
    """Allowed operations in the VERIFICATION phase."""
    VERIFY_RECORD_ABSENT = "VERIFY_RECORD_ABSENT"
    VERIFY_RECORD_PRESENT = "VERIFY_RECORD_PRESENT"
    VERIFY_RECORD_REDACTED = "VERIFY_RECORD_REDACTED"
    VERIFY_RECORD_ANONYMIZED = "VERIFY_RECORD_ANONYMIZED"
    VERIFY_DATA_FLOW_DISABLED = "VERIFY_DATA_FLOW_DISABLED"
    VERIFY_RESTORE_BLOCKED = "VERIFY_RESTORE_BLOCKED"


class State(str, Enum):
    """Allowed states for step resources."""
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    BLOCKED = "BLOCKED"
    REDACTED = "REDACTED"
    ANONYMIZED = "ANONYMIZED"


class ReportedStatus(str, Enum):
    """Status claimed by the upstream deletion workflow."""
    COMPLETE = "COMPLETE"
    PARTIALLY_COMPLETE = "PARTIALLY_COMPLETE"
    NOT_STARTED = "NOT_STARTED"


class DataCategory(str, Enum):
    """Data categories defined in deletion_rules.csv."""
    USER_PROFILE = "USER_PROFILE"
    SECONDARY_IDENTIFIER = "SECONDARY_IDENTIFIER"
    SEARCH_INDEX_ENTRY = "SEARCH_INDEX_ENTRY"
    CACHE_ENTRY = "CACHE_ENTRY"
    SUPPORT_MESSAGE = "SUPPORT_MESSAGE"
    SUPPORT_ATTACHMENT = "SUPPORT_ATTACHMENT"
    ANALYTICS_PROFILE = "ANALYTICS_PROFILE"
    PRODUCT_TELEMETRY = "PRODUCT_TELEMETRY"
    USER_EXPORT = "USER_EXPORT"
    MARKETING_PROFILE = "MARKETING_PROFILE"
    EMAIL_DELIVERY_LOG = "EMAIL_DELIVERY_LOG"
    SECURITY_AUDIT_LOG = "SECURITY_AUDIT_LOG"
    LEGAL_HOLD_RECORD = "LEGAL_HOLD_RECORD"
    BACKUP_ARCHIVE = "BACKUP_ARCHIVE"
    ACCOUNT_TOMBSTONE = "ACCOUNT_TOMBSTONE"


class RequiredAction(str, Enum):
    """Actions defined in deletion_rules.csv."""
    DELETE = "DELETE"
    REDACT = "REDACT"
    ANONYMIZE = "ANONYMIZE"
    RETAIN = "RETAIN"


# Phase ordering index for deterministic sorting
PHASE_ORDER: dict[Phase, int] = {
    Phase.FINDING: 1,
    Phase.REMEDIATION: 2,
    Phase.VERIFICATION: 3,
}

# Official operation ordering within each phase
OPERATION_ORDER: dict[str, int] = {
    # FINDING operations
    FindingOperation.REPORT_REMAINING_RECORD.value: 1,
    FindingOperation.REPORT_EXPOSED_PII.value: 2,
    FindingOperation.REPORT_ACTIVE_DATA_FLOW.value: 3,
    FindingOperation.REPORT_RESTORE_RISK.value: 4,

    # REMEDIATION operations
    RemediationOperation.DISABLE_DATA_FLOW.value: 1,
    RemediationOperation.BLOCK_RESTORE.value: 2,
    RemediationOperation.DELETE_RECORD.value: 3,
    RemediationOperation.REDACT_RECORD.value: 4,
    RemediationOperation.ANONYMIZE_RECORD.value: 5,

    # VERIFICATION operations
    VerificationOperation.VERIFY_RECORD_ABSENT.value: 1,
    VerificationOperation.VERIFY_RECORD_PRESENT.value: 2,
    VerificationOperation.VERIFY_RECORD_REDACTED.value: 3,
    VerificationOperation.VERIFY_RECORD_ANONYMIZED.value: 4,
    VerificationOperation.VERIFY_DATA_FLOW_DISABLED.value: 5,
    VerificationOperation.VERIFY_RESTORE_BLOCKED.value: 6,
}

# Strict 1-to-1 mapping of allowed state for each operation
ALLOWED_OPERATION_STATES: dict[str, State] = {
    FindingOperation.REPORT_REMAINING_RECORD.value: State.PRESENT,
    FindingOperation.REPORT_EXPOSED_PII.value: State.PRESENT,
    FindingOperation.REPORT_ACTIVE_DATA_FLOW.value: State.ACTIVE,
    FindingOperation.REPORT_RESTORE_RISK.value: State.ACTIVE,

    RemediationOperation.DISABLE_DATA_FLOW.value: State.DISABLED,
    RemediationOperation.BLOCK_RESTORE.value: State.BLOCKED,
    RemediationOperation.DELETE_RECORD.value: State.ABSENT,
    RemediationOperation.REDACT_RECORD.value: State.REDACTED,
    RemediationOperation.ANONYMIZE_RECORD.value: State.ANONYMIZED,

    VerificationOperation.VERIFY_RECORD_ABSENT.value: State.ABSENT,
    VerificationOperation.VERIFY_RECORD_PRESENT.value: State.PRESENT,
    VerificationOperation.VERIFY_RECORD_REDACTED.value: State.REDACTED,
    VerificationOperation.VERIFY_RECORD_ANONYMIZED.value: State.ANONYMIZED,
    VerificationOperation.VERIFY_DATA_FLOW_DISABLED.value: State.DISABLED,
    VerificationOperation.VERIFY_RESTORE_BLOCKED.value: State.BLOCKED,
}

# Operations grouped by allowed phase
PHASE_ALLOWED_OPERATIONS: dict[Phase, set[str]] = {
    Phase.FINDING: {op.value for op in FindingOperation},
    Phase.REMEDIATION: {op.value for op in RemediationOperation},
    Phase.VERIFICATION: {op.value for op in VerificationOperation},
}
