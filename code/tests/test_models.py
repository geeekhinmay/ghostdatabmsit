"""Unit tests for code.models.enums and code.models.schemas."""

import pytest
from pydantic import ValidationError

from code.models.enums import (
    ALLOWED_OPERATION_STATES,
    OPERATION_ORDER,
    PHASE_ALLOWED_OPERATIONS,
    PHASE_ORDER,
    DeletionStatus,
    FindingOperation,
    Phase,
    RemediationOperation,
    ReportedStatus,
    State,
    VerificationOperation,
)
from code.models.schemas import OutputRow, Step


def test_enums_completeness():
    """Verify all 15 official operations are present and mapped to valid states."""
    assert len(FindingOperation) == 4
    assert len(RemediationOperation) == 5
    assert len(VerificationOperation) == 6

    total_ops = len(FindingOperation) + len(RemediationOperation) + len(VerificationOperation)
    assert total_ops == 15
    assert len(ALLOWED_OPERATION_STATES) == 15
    assert len(OPERATION_ORDER) == 15


def test_step_valid_creation():
    """Verify valid Step creation for each phase."""
    finding_step = Step(
        step_no=1,
        phase=Phase.FINDING,
        system_id="account_service",
        resource_id="account_001",
        operation=FindingOperation.REPORT_REMAINING_RECORD.value,
        state=State.PRESENT,
        evidence_id="evidence_54",
    )
    assert finding_step.step_no == 1
    assert finding_step.operation == "REPORT_REMAINING_RECORD"
    assert finding_step.state == State.PRESENT

    remediation_step = Step(
        step_no=2,
        phase=Phase.REMEDIATION,
        system_id="account_service",
        resource_id="account_001",
        operation=RemediationOperation.DELETE_RECORD.value,
        state=State.ABSENT,
        evidence_id="",
    )
    assert remediation_step.evidence_id == ""

    verification_step = Step(
        step_no=3,
        phase=Phase.VERIFICATION,
        system_id="account_service",
        resource_id="account_001",
        operation=VerificationOperation.VERIFY_RECORD_ABSENT.value,
        state=State.ABSENT,
        evidence_id="",
    )
    assert verification_step.operation == "VERIFY_RECORD_ABSENT"


def test_step_invalid_operation_for_phase():
    """Step with an operation not permitted in its phase should raise ValidationError."""
    with pytest.raises(ValidationError):
        Step(
            step_no=1,
            phase=Phase.FINDING,
            system_id="account_service",
            resource_id="account_001",
            operation=RemediationOperation.DELETE_RECORD.value,  # not a finding!
            state=State.ABSENT,
            evidence_id="evidence_01",
        )


def test_step_mismatched_state():
    """Step with mismatched state for operation should raise ValidationError."""
    with pytest.raises(ValidationError):
        Step(
            step_no=1,
            phase=Phase.FINDING,
            system_id="account_service",
            resource_id="account_001",
            operation=FindingOperation.REPORT_REMAINING_RECORD.value,
            state=State.ABSENT,  # should be PRESENT!
            evidence_id="evidence_01",
        )


def test_remediation_non_empty_evidence_id_fails():
    """Remediation steps must have empty evidence_id."""
    with pytest.raises(ValidationError):
        Step(
            step_no=1,
            phase=Phase.REMEDIATION,
            system_id="account_service",
            resource_id="account_001",
            operation=RemediationOperation.DELETE_RECORD.value,
            state=State.ABSENT,
            evidence_id="evidence_01",  # Forbidden in remediation!
        )


def test_output_row_not_applicable_must_have_empty_steps():
    """OutputRow with NOT_APPLICABLE must have empty steps_json."""
    valid_row = OutputRow(
        case_id="case_000",
        deletion_status=DeletionStatus.NOT_APPLICABLE,
        steps_json=[],
    )
    assert valid_row.deletion_status == DeletionStatus.NOT_APPLICABLE

    step = Step(
        step_no=1,
        phase=Phase.VERIFICATION,
        system_id="account_service",
        resource_id="acc_1",
        operation="VERIFY_RECORD_ABSENT",
        state=State.ABSENT,
        evidence_id="ev_1",
    )
    with pytest.raises(ValidationError):
        OutputRow(
            case_id="case_000",
            deletion_status=DeletionStatus.NOT_APPLICABLE,
            steps_json=[step],
        )
