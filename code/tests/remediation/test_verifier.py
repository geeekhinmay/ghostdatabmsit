"""
Unit tests for verification step generation module (code/verification/verifier.py).
"""

import pytest

from code.models.enums import DeletionStatus, StepOperation, StepPhase, StepState
from code.policy.evaluator import evaluate_policy
from code.remediation.planner import build_remediation_plan
from code.verification.verifier import build_verification_steps


def test_verification_empty_for_not_applicable():
    """Non-deletion requests must produce zero verification steps."""
    policy_na = {"deletion_status": DeletionStatus.NOT_APPLICABLE, "verification_items": []}
    assert build_verification_steps({}, {}, policy_na) == []


def test_verification_for_complete_case_has_evidence_ids():
    """
    For a COMPLETE case, verification steps must prove the current state
    and MUST have non-empty participant-visible evidence_ids.
    """
    req = {"case_id": "case_03", "request_text": "Please delete my account."}
    investigation = {
        "records": [
            {
                "system_id": "account_service",
                "resource_id": "account_7566",
                "state": "ABSENT",
                "evidence_id": "evidence_94",
            },
            {
                "system_id": "security_service",
                "resource_id": "audit_record_2016",
                "state": "PRESENT",
                "evidence_id": "evidence_94",
            },
            {
                "system_id": "analytics_platform",
                "resource_id": "analytics_9406",
                "state": "ANONYMIZED",
                "is_attributable": False,
                "evidence_id": "evidence_94",
            },
        ]
    }

    policy = evaluate_policy(req, investigation)
    assert policy.deletion_status == DeletionStatus.COMPLETE

    v_steps = build_verification_steps(req, investigation, policy)
    assert len(v_steps) == 3

    for step in v_steps:
        assert step.phase == StepPhase.VERIFICATION
        assert step.evidence_id == "evidence_94", "COMPLETE steps must cite evidence"

    # Operation order: VERIFY_RECORD_ABSENT (1), VERIFY_RECORD_PRESENT (2), VERIFY_RECORD_ANONYMIZED (4)
    ops = [s.operation for s in v_steps]
    assert ops == [
        StepOperation.VERIFY_RECORD_ABSENT,
        StepOperation.VERIFY_RECORD_PRESENT,
        StepOperation.VERIFY_RECORD_ANONYMIZED,
    ]
    assert [s.step_no for s in v_steps] == [1, 2, 3]


def test_verification_for_incomplete_case_has_empty_evidence_ids():
    """
    For an INCOMPLETE case, future verification steps must have empty evidence_ids (evidence_id="").
    """
    req = {"case_id": "case_05", "request_text": "Please delete my profile."}
    investigation = {
        "records": [
            {
                "system_id": "account_service",
                "resource_id": "account_005",
                "state": "PRESENT",
                "evidence_id": "evidence_54",
            }
        ]
    }

    policy = evaluate_policy(req, investigation)
    assert policy.deletion_status == DeletionStatus.INCOMPLETE

    plan = build_remediation_plan(req, investigation, policy)
    v_steps = build_verification_steps(req, investigation, policy)

    assert len(v_steps) == 1
    v = v_steps[0]
    assert v.phase == StepPhase.VERIFICATION
    assert v.operation == StepOperation.VERIFY_RECORD_ABSENT
    assert v.resource_id == "account_005"
    assert v.evidence_id == ""  # Future verification must be empty string

    # Step numbers: finding is 1, remediation is 2, verification is 3
    assert policy.findings[0].step_no == 1
    assert plan[0].step_no == 2
    assert v.step_no == 3


def test_verification_official_operation_order():
    """
    Verify complete 6-operation ordering in VERIFICATION phase:
    1. VERIFY_RECORD_ABSENT
    2. VERIFY_RECORD_PRESENT
    3. VERIFY_RECORD_REDACTED
    4. VERIFY_RECORD_ANONYMIZED
    5. VERIFY_DATA_FLOW_DISABLED
    6. VERIFY_RESTORE_BLOCKED
    """
    policy = {
        "deletion_status": DeletionStatus.COMPLETE,
        "verification_items": [
            {"system_id": "backup_service", "resource_id": "backup_01", "operation": StepOperation.VERIFY_RESTORE_BLOCKED, "state": StepState.BLOCKED, "evidence_id": "ev_01"},
            {"system_id": "integration_service", "resource_id": "flow_01", "operation": StepOperation.VERIFY_DATA_FLOW_DISABLED, "state": StepState.DISABLED, "evidence_id": "ev_01"},
            {"system_id": "analytics_platform", "resource_id": "analytics_01", "operation": StepOperation.VERIFY_RECORD_ANONYMIZED, "state": StepState.ANONYMIZED, "evidence_id": "ev_01"},
            {"system_id": "support_platform", "resource_id": "support_01", "operation": StepOperation.VERIFY_RECORD_REDACTED, "state": StepState.REDACTED, "evidence_id": "ev_01"},
            {"system_id": "security_service", "resource_id": "audit_01", "operation": StepOperation.VERIFY_RECORD_PRESENT, "state": StepState.PRESENT, "evidence_id": "ev_01"},
            {"system_id": "account_service", "resource_id": "account_01", "operation": StepOperation.VERIFY_RECORD_ABSENT, "state": StepState.ABSENT, "evidence_id": "ev_01"},
        ]
    }

    steps = build_verification_steps({}, {}, policy)
    assert len(steps) == 6

    expected_ops = [
        StepOperation.VERIFY_RECORD_ABSENT,
        StepOperation.VERIFY_RECORD_PRESENT,
        StepOperation.VERIFY_RECORD_REDACTED,
        StepOperation.VERIFY_RECORD_ANONYMIZED,
        StepOperation.VERIFY_DATA_FLOW_DISABLED,
        StepOperation.VERIFY_RESTORE_BLOCKED,
    ]
    assert [s.operation for s in steps] == expected_ops
    assert [s.step_no for s in steps] == [1, 2, 3, 4, 5, 6]
