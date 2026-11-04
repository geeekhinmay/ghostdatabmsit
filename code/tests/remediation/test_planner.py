"""
Unit tests for remediation planning module (code/remediation/planner.py).
"""

import pytest

from code.models.enums import DeletionStatus, StepOperation, StepPhase, StepState
from code.policy.evaluator import evaluate_policy
from code.remediation.planner import build_remediation_plan


def test_remediation_empty_for_complete_and_not_applicable():
    """Remediation plan must be empty for COMPLETE and NOT_APPLICABLE cases."""
    # NOT_APPLICABLE
    policy_na = {"deletion_status": DeletionStatus.NOT_APPLICABLE, "findings": [], "remediation_items": []}
    assert build_remediation_plan({}, {}, policy_na) == []

    # COMPLETE
    policy_comp = {"deletion_status": DeletionStatus.COMPLETE, "findings": [], "remediation_items": []}
    assert build_remediation_plan({}, {}, policy_comp) == []


def test_remediation_official_ordering():
    """
    Verify strict official operation order:
    1. DISABLE_DATA_FLOW
    2. BLOCK_RESTORE
    3. DELETE_RECORD
    4. REDACT_RECORD
    5. ANONYMIZE_RECORD
    followed by system_id ASC, resource_id ASC.
    """
    req = {"case_id": "case_11", "request_text": "Please delete my account and data."}
    investigation = {
        "records": [
            {
                "system_id": "search_service",
                "resource_id": "search_052",
                "state": "PRESENT",
                "evidence_id": "evidence_03",
            },
            {
                "system_id": "analytics_platform",
                "resource_id": "analytics_2034",
                "state": "PRESENT",
                "is_attributable": True,
                "evidence_id": "evidence_03",
            },
            {
                "system_id": "support_platform",
                "resource_id": "support_864",
                "state": "PRESENT",
                "has_exposed_pii": True,
                "evidence_id": "evidence_03",
            },
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
                "resource_id": "backup_1001",
                "is_blocked": False,
                "evidence_id": "evidence_03",
            }
        ],
    }

    policy = evaluate_policy(req, investigation)
    plan = build_remediation_plan(req, investigation, policy)

    assert len(plan) == 5

    # Check phase
    for step in plan:
        assert step.phase == StepPhase.REMEDIATION
        assert step.evidence_id == ""  # Proposed remediation uses empty evidence_id

    # Verify operation ordering
    ops = [s.operation for s in plan]
    assert ops == [
        StepOperation.DISABLE_DATA_FLOW,
        StepOperation.BLOCK_RESTORE,
        StepOperation.DELETE_RECORD,
        StepOperation.REDACT_RECORD,
        StepOperation.ANONYMIZE_RECORD,
    ]

    # Verify step numbers follow findings consecutively
    finding_count = len(policy.findings)
    expected_step_nos = list(range(finding_count + 1, finding_count + 1 + len(plan)))
    assert [s.step_no for s in plan] == expected_step_nos


def test_remediation_secondary_sorting_by_system_and_resource():
    """Within same operation, items must be sorted by system_id ASC, then resource_id ASC."""
    policy = {
        "deletion_status": DeletionStatus.INCOMPLETE,
        "findings": [{"dummy": True}],
        "remediation_items": [
            {
                "system_id": "search_service",
                "resource_id": "search_999",
                "operation": StepOperation.DELETE_RECORD,
                "state": StepState.ABSENT,
            },
            {
                "system_id": "account_service",
                "resource_id": "account_005",
                "operation": StepOperation.DELETE_RECORD,
                "state": StepState.ABSENT,
            },
            {
                "system_id": "search_service",
                "resource_id": "search_001",
                "operation": StepOperation.DELETE_RECORD,
                "state": StepState.ABSENT,
            },
        ],
    }

    plan = build_remediation_plan({}, {}, policy, start_step_no=2)
    assert len(plan) == 3

    # Expected order: account_service/account_005, search_service/search_001, search_service/search_999
    assert plan[0].system_id == "account_service" and plan[0].resource_id == "account_005"
    assert plan[1].system_id == "search_service" and plan[1].resource_id == "search_001"
    assert plan[2].system_id == "search_service" and plan[2].resource_id == "search_999"
    assert [s.step_no for s in plan] == [2, 3, 4]
