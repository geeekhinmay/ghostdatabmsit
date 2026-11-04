"""
Integration test comparing policy, remediation, and verification output
with sample cases from dataset/sample_output.csv.
"""

import json
import pytest
from pathlib import Path

from code.models.enums import DeletionStatus, StepOperation, StepPhase, StepState
from code.policy.evaluator import evaluate_policy
from code.remediation.planner import build_remediation_plan
from code.verification.verifier import build_verification_steps


def test_sample_case_01_complete():
    """Verify case_01 (COMPLETE case with 1 verification step)."""
    req = {
        "case_id": "case_01",
        "request_text": "Hi, I haven't used this account in years and would like it closed. Please remove the profile and the personal details attached to it.",
    }
    investigation = {
        "records": [
            {
                "system_id": "account_service",
                "resource_id": "account_001",
                "state": "ABSENT",
                "evidence_id": "evidence_54",
            }
        ]
    }

    policy = evaluate_policy(req, investigation, None)
    assert policy.deletion_status == DeletionStatus.COMPLETE

    remediation = build_remediation_plan(req, investigation, policy)
    assert remediation == []

    verification = build_verification_steps(req, investigation, policy)
    assert len(verification) == 1
    assert verification[0].operation == StepOperation.VERIFY_RECORD_ABSENT
    assert verification[0].resource_id == "account_001"
    assert verification[0].evidence_id == "evidence_54"
    assert verification[0].step_no == 1


def test_sample_case_05_incomplete():
    """Verify case_05 (INCOMPLETE case: remaining account_005)."""
    req = {
        "case_id": "case_05",
        "request_text": "I deleted this account and received a confirmation, but the same email address is still recognized. Please remove any remaining copy of my profile.",
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

    policy = evaluate_policy(req, investigation, None)
    assert policy.deletion_status == DeletionStatus.INCOMPLETE
    assert len(policy.findings) == 1
    assert policy.findings[0].operation == StepOperation.REPORT_REMAINING_RECORD
    assert policy.findings[0].step_no == 1

    remediation = build_remediation_plan(req, investigation, policy)
    assert len(remediation) == 1
    assert remediation[0].operation == StepOperation.DELETE_RECORD
    assert remediation[0].evidence_id == ""
    assert remediation[0].step_no == 2

    verification = build_verification_steps(req, investigation, policy)
    assert len(verification) == 1
    assert verification[0].operation == StepOperation.VERIFY_RECORD_ABSENT
    assert verification[0].evidence_id == ""
    assert verification[0].step_no == 3


def test_sample_case_11_complex():
    """Verify case_11 complex multi-resource incomplete case."""
    req = {
        "case_id": "case_11",
        "request_text": "I would like the account associated with this address to be erased. Please handle any copies that fall within the scope of the deletion request.",
    }
    investigation = {
        "records": [
            {
                "system_id": "account_service",
                "resource_id": "account_4248",
                "state": "ABSENT",
                "evidence_id": "",
            },
            {
                "system_id": "search_service",
                "resource_id": "search_052",
                "state": "PRESENT",
                "evidence_id": "evidence_03",
            },
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
            {
                "system_id": "security_service",
                "resource_id": "audit_record_9394",
                "state": "PRESENT",
                "evidence_id": "",
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
    }

    policy = evaluate_policy(req, investigation, None)
    assert policy.deletion_status == DeletionStatus.INCOMPLETE
    assert len(policy.findings) == 4

    # Findings operation order:
    # REPORT_REMAINING_RECORD (search_052)
    # REPORT_EXPOSED_PII (analytics_2034, support_864)
    # REPORT_ACTIVE_DATA_FLOW (data_flow_9522)
    ops_findings = [f.operation for f in policy.findings]
    assert ops_findings == [
        StepOperation.REPORT_REMAINING_RECORD,
        StepOperation.REPORT_EXPOSED_PII,
        StepOperation.REPORT_EXPOSED_PII,
        StepOperation.REPORT_ACTIVE_DATA_FLOW,
    ]

    remediation = build_remediation_plan(req, investigation, policy)
    assert len(remediation) == 4

    # Remediation operation order:
    # DISABLE_DATA_FLOW (data_flow_9522)
    # DELETE_RECORD (search_052)
    # REDACT_RECORD (support_864)
    # ANONYMIZE_RECORD (analytics_2034)
    ops_rem = [r.operation for r in remediation]
    assert ops_rem == [
        StepOperation.DISABLE_DATA_FLOW,
        StepOperation.DELETE_RECORD,
        StepOperation.REDACT_RECORD,
        StepOperation.ANONYMIZE_RECORD,
    ]

    verification = build_verification_steps(req, investigation, policy)
    assert len(verification) == 6

    # Consecutive numbering across all steps:
    # 4 findings (1..4) + 4 remediation (5..8) + 6 verification (9..14) = 14 total steps
    all_steps = policy.findings + remediation + verification
    assert [s.step_no for s in all_steps] == list(range(1, 15))


def test_steps_json_serializability():
    """Verify that returned AuditStep objects serialize to JSON matching grading contract."""
    from code.models.schemas import AuditStep

    step = AuditStep(
        step_no=1,
        phase=StepPhase.FINDING,
        system_id="account_service",
        resource_id="account_005",
        operation=StepOperation.REPORT_REMAINING_RECORD,
        state=StepState.PRESENT,
        evidence_id="evidence_54",
    )

    dumped = step.model_dump()
    json_str = json.dumps(dumped)
    parsed = json.loads(json_str)

    assert parsed["step_no"] == 1
    assert parsed["phase"] == "FINDING"
    assert parsed["system_id"] == "account_service"
    assert parsed["resource_id"] == "account_005"
    assert parsed["operation"] == "REPORT_REMAINING_RECORD"
    assert parsed["state"] == "PRESENT"
    assert parsed["evidence_id"] == "evidence_54"
