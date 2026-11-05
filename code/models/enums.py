"""Shared enumerations for the Ghost Data Still Exists deletion-audit system.

Owned by: Member 1 (Team Lead)
Read by: All modules.
"""

from __future__ import annotations

from enum import Enum


class DeletionStatus(str, Enum):
    """Top-level deletion audit outcome."""
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class StepPhase(str, Enum):
    """Allowed step phases. Order is strictly FINDING -> REMEDIATION -> VERIFICATION."""
    FINDING = "FINDING"
    REMEDIATION = "REMEDIATION"
    VERIFICATION = "VERIFICATION"


# Alias for backwards compatibility with Member 1 modules
Phase = StepPhase


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


class StepOperation(str, Enum):
    """Combined allowed step operations across all three phases."""
    # Findings
    REPORT_REMAINING_RECORD = "REPORT_REMAINING_RECORD"
    REPORT_EXPOSED_PII = "REPORT_EXPOSED_PII"
    REPORT_ACTIVE_DATA_FLOW = "REPORT_ACTIVE_DATA_FLOW"
    REPORT_RESTORE_RISK = "REPORT_RESTORE_RISK"
    # Remediation
    DISABLE_DATA_FLOW = "DISABLE_DATA_FLOW"
    BLOCK_RESTORE = "BLOCK_RESTORE"
    DELETE_RECORD = "DELETE_RECORD"
    REDACT_RECORD = "REDACT_RECORD"
    ANONYMIZE_RECORD = "ANONYMIZE_RECORD"
    # Verification
    VERIFY_RECORD_ABSENT = "VERIFY_RECORD_ABSENT"
    VERIFY_RECORD_PRESENT = "VERIFY_RECORD_PRESENT"
    VERIFY_RECORD_REDACTED = "VERIFY_RECORD_REDACTED"
    VERIFY_RECORD_ANONYMIZED = "VERIFY_RECORD_ANONYMIZED"
    VERIFY_DATA_FLOW_DISABLED = "VERIFY_DATA_FLOW_DISABLED"
    VERIFY_RESTORE_BLOCKED = "VERIFY_RESTORE_BLOCKED"


class StepState(str, Enum):
    """Allowed step states."""
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    REDACTED = "REDACTED"
    ANONYMIZED = "ANONYMIZED"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    BLOCKED = "BLOCKED"


# Alias for backwards compatibility with Member 1 modules
State = StepState


class ReportedStatus(str, Enum):
    """Status claimed by the deletion workflow."""
    COMPLETE = "COMPLETE"
    PARTIALLY_COMPLETE = "PARTIALLY_COMPLETE"
    NOT_STARTED = "NOT_STARTED"


class RequiredAction(str, Enum):
    """Required action from deletion_rules.csv."""
    DELETE = "DELETE"
    REDACT = "REDACT"
    ANONYMIZE = "ANONYMIZE"
    RETAIN = "RETAIN"


class EvidenceFormat(str, Enum):
    """Parsed evidence file format."""
    CSV = "csv"
    TSV = "tsv"
    JSON = "json"
    JSONL = "jsonl"
    SQL = "sql"
    LOG = "log"
    TXT = "txt"
    PDF = "pdf"
    PNG = "png"
    JPG = "jpg"
    UNKNOWN = "unknown"


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


# Phase ordering index for deterministic sorting
PHASE_ORDER: dict[StepPhase, int] = {
    StepPhase.FINDING: 1,
    StepPhase.REMEDIATION: 2,
    StepPhase.VERIFICATION: 3,
}

# Official operation ordering within each phase
OPERATION_ORDER: dict[str, int] = {
    # FINDING operations
    StepOperation.REPORT_REMAINING_RECORD.value: 1,
    StepOperation.REPORT_EXPOSED_PII.value: 2,
    StepOperation.REPORT_ACTIVE_DATA_FLOW.value: 3,
    StepOperation.REPORT_RESTORE_RISK.value: 4,

    # REMEDIATION operations
    StepOperation.DISABLE_DATA_FLOW.value: 1,
    StepOperation.BLOCK_RESTORE.value: 2,
    StepOperation.DELETE_RECORD.value: 3,
    StepOperation.REDACT_RECORD.value: 4,
    StepOperation.ANONYMIZE_RECORD.value: 5,

    # VERIFICATION operations
    StepOperation.VERIFY_RECORD_ABSENT.value: 1,
    StepOperation.VERIFY_RECORD_PRESENT.value: 2,
    StepOperation.VERIFY_RECORD_REDACTED.value: 3,
    StepOperation.VERIFY_RECORD_ANONYMIZED.value: 4,
    StepOperation.VERIFY_DATA_FLOW_DISABLED.value: 5,
    StepOperation.VERIFY_RESTORE_BLOCKED.value: 6,
}

# Strict 1-to-1 mapping of allowed state for each operation
ALLOWED_OPERATION_STATES: dict[str, StepState] = {
    StepOperation.REPORT_REMAINING_RECORD.value: StepState.PRESENT,
    StepOperation.REPORT_EXPOSED_PII.value: StepState.PRESENT,
    StepOperation.REPORT_ACTIVE_DATA_FLOW.value: StepState.ACTIVE,
    StepOperation.REPORT_RESTORE_RISK.value: StepState.ACTIVE,

    StepOperation.DISABLE_DATA_FLOW.value: StepState.DISABLED,
    StepOperation.BLOCK_RESTORE.value: StepState.BLOCKED,
    StepOperation.DELETE_RECORD.value: StepState.ABSENT,
    StepOperation.REDACT_RECORD.value: StepState.REDACTED,
    StepOperation.ANONYMIZE_RECORD.value: StepState.ANONYMIZED,

    StepOperation.VERIFY_RECORD_ABSENT.value: StepState.ABSENT,
    StepOperation.VERIFY_RECORD_PRESENT.value: StepState.PRESENT,
    StepOperation.VERIFY_RECORD_REDACTED.value: StepState.REDACTED,
    StepOperation.VERIFY_RECORD_ANONYMIZED.value: StepState.ANONYMIZED,
    StepOperation.VERIFY_DATA_FLOW_DISABLED.value: StepState.DISABLED,
    StepOperation.VERIFY_RESTORE_BLOCKED.value: StepState.BLOCKED,
}

# Operations grouped by allowed phase
PHASE_ALLOWED_OPERATIONS: dict[StepPhase, set[str]] = {
    StepPhase.FINDING: {op.value for op in FindingOperation},
    StepPhase.REMEDIATION: {op.value for op in RemediationOperation},
    StepPhase.VERIFICATION: {op.value for op in VerificationOperation},
}
