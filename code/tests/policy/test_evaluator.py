"""
Unit tests for policy evaluation engine (code/policy/evaluator.py).
"""

import pytest
from datetime import datetime

from code.models.enums import (
    DeletionStatus,
    ReportedStatus,
    StepOperation,
    StepPhase,
    StepState,
)
from code.models.schemas import DeletionRequest
from code.policy.evaluator import evaluate_policy


def test_evaluate_policy_non_deletion():
    """Non-deletion requests must return NOT_APPLICABLE and zero findings."""
    req = {
        "case_id": "case_non_del",
        "request_text": "Please provide a copy of all my data under GDPR SAR.",
    }
    decision = evaluate_policy(req, {})
    assert decision.deletion_status == DeletionStatus.NOT_APPLICABLE
    assert decision.is_deletion_request is False
    assert len(decision.findings) == 0
    assert len(decision.remediation_items) == 0
    assert len(decision.verification_items) == 0


def test_evaluate_policy_complete_case():
    """A fully compliant deletion case must evaluate to COMPLETE with zero findings."""
    req = {
        "case_id": "case_complete",
        "request_text": "Please delete my account and personal data.",
    }
    investigation = {
        "records": [
            {
                "system_id": "account_service",
                "resource_id": "account_001",
                "state": "ABSENT",
                "evidence_id": "evidence_54",
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
        ],
        "data_flows": [
            {
                "system_id": "integration_service",
                "resource_id": "data_flow_101",
                "is_active": False,
                "evidence_id": "evidence_94",
            }
        ],
        "restore_risks": [
            {
                "system_id": "backup_service",
                "resource_id": "backup_201",
                "is_blocked": True,
                "evidence_id": "evidence_94",
            }
        ],
    }

    decision = evaluate_policy(req, investigation)
    assert decision.deletion_status == DeletionStatus.COMPLETE
    assert decision.is_deletion_request is True
    assert len(decision.findings) == 0
    assert len(decision.verification_items) == 5


def test_evaluate_policy_incomplete_remaining_record():
    """When a deletable record still exists, status must be INCOMPLETE with REPORT_REMAINING_RECORD."""
    req = {
        "case_id": "case_rem",
        "request_text": "Please remove my profile completely.",
    }
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

    decision = evaluate_policy(req, investigation)
    assert decision.deletion_status == DeletionStatus.INCOMPLETE
    assert len(decision.findings) == 1
    finding = decision.findings[0]
    assert finding.phase == StepPhase.FINDING
    assert finding.operation == StepOperation.REPORT_REMAINING_RECORD
    assert finding.state == StepState.PRESENT
    assert finding.resource_id == "account_005"
    assert finding.evidence_id == "evidence_54"
    assert finding.step_no == 1


def test_evaluate_policy_incomplete_exposed_pii():
    """When a support message or analytics profile exposes PII, REPORT_EXPOSED_PII finding is produced."""
    req = {
        "case_id": "case_exp",
        "request_text": "Please delete my account and clean support messages.",
    }
    investigation = {
        "records": [
            {
                "system_id": "support_platform",
                "resource_id": "support_864",
                "state": "PRESENT",
                "has_exposed_pii": True,
                "evidence_id": "evidence_03",
            },
            {
                "system_id": "analytics_platform",
                "resource_id": "analytics_2034",
                "state": "PRESENT",
                "is_attributable": True,
                "evidence_id": "evidence_03",
            },
        ]
    }

    decision = evaluate_policy(req, investigation)
    assert decision.deletion_status == DeletionStatus.INCOMPLETE
    assert len(decision.findings) == 2
    for f in decision.findings:
        assert f.operation == StepOperation.REPORT_EXPOSED_PII
        assert f.state == StepState.PRESENT


def test_evaluate_policy_active_data_flow_and_restore_risk():
    """Active data flows and restore risks produce proper findings and ordering."""
    req = {
        "case_id": "case_risk",
        "request_text": "Please permanently erase my account.",
    }
    investigation = {
        "records": [
            {
                "system_id": "search_service",
                "resource_id": "search_052",
                "state": "PRESENT",
                "evidence_id": "evidence_03",
            }
        ],
        "data_flows": [
            {
                "system_id": "integration_service",
                "resource_id": "data_flow_9522",
                "is_active": True,
                "evidence_id": "evidence_03",
            }
        ],
        "restore_risks": [
            {
                "system_id": "backup_service",
                "resource_id": "backup_4978",
                "is_blocked": False,
                "evidence_id": "evidence_93",
            }
        ],
    }

    decision = evaluate_policy(req, investigation)
    assert decision.deletion_status == DeletionStatus.INCOMPLETE
    assert len(decision.findings) == 3

    # Check official finding ordering:
    # 1. REPORT_REMAINING_RECORD
    # 2. REPORT_ACTIVE_DATA_FLOW
    # 3. REPORT_RESTORE_RISK
    ops = [f.operation for f in decision.findings]
    assert ops == [
        StepOperation.REPORT_REMAINING_RECORD,
        StepOperation.REPORT_ACTIVE_DATA_FLOW,
        StepOperation.REPORT_RESTORE_RISK,
    ]

    # Check consecutive step numbers
    assert [f.step_no for f in decision.findings] == [1, 2, 3]


def test_evaluate_policy_with_deletion_request_model():
    """Verify compatibility when input is a typed DeletionRequest instance."""
    now = datetime(2026, 9, 1, 12, 0)
    req = DeletionRequest(
        case_id="case_typed_01",
        email="user@example.com",
        requested_at=now,
        reported_status=ReportedStatus.COMPLETE,
        reported_at=now,
        audit_at=now,
        request_text="Please delete my account and remove my personal details.",
    )
    decision = evaluate_policy(req, {"records": []})
    assert decision.case_id == "case_typed_01"
    assert decision.deletion_status == DeletionStatus.COMPLETE
