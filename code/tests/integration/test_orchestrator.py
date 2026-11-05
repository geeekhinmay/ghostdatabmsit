"""Integration tests for the central Orchestrator."""

from pathlib import Path
import pytest

from code.models.enums import DeletionStatus, FindingOperation, Phase, RemediationOperation, State, VerificationOperation
from code.models.schemas import DatasetBundle, DeletionRequest, InvestigationFinding, Step
from code.orchestrator import Orchestrator, sort_and_number_steps
from code.output.validator import validate_output
from config.settings import AppConfig


def test_sort_and_number_steps_official_ordering():
    """Verify that sort_and_number_steps strictly enforces official order:
    FINDING -> REMEDIATION -> VERIFICATION, then operation order, then system_id, resource_id.
    """
    input_steps = [
        # Verification step
        Step(
            step_no=99,
            phase=Phase.VERIFICATION,
            system_id="support_platform",
            resource_id="support_864",
            operation=VerificationOperation.VERIFY_RECORD_REDACTED.value,
            state=State.REDACTED,
            evidence_id="",
        ),
        # Remediation step 2
        Step(
            step_no=88,
            phase=Phase.REMEDIATION,
            system_id="search_service",
            resource_id="search_052",
            operation=RemediationOperation.DELETE_RECORD.value,
            state=State.ABSENT,
            evidence_id="",
        ),
        # Remediation step 1 (DISABLE_DATA_FLOW should come before DELETE_RECORD)
        Step(
            step_no=77,
            phase=Phase.REMEDIATION,
            system_id="integration_service",
            resource_id="data_flow_9522",
            operation=RemediationOperation.DISABLE_DATA_FLOW.value,
            state=State.DISABLED,
            evidence_id="",
        ),
        # Finding step 2 (REPORT_EXPOSED_PII)
        Step(
            step_no=66,
            phase=Phase.FINDING,
            system_id="analytics_platform",
            resource_id="analytics_2034",
            operation=FindingOperation.REPORT_EXPOSED_PII.value,
            state=State.PRESENT,
            evidence_id="evidence_03",
        ),
        # Finding step 1 (REPORT_REMAINING_RECORD should come before REPORT_EXPOSED_PII)
        Step(
            step_no=55,
            phase=Phase.FINDING,
            system_id="search_service",
            resource_id="search_052",
            operation=FindingOperation.REPORT_REMAINING_RECORD.value,
            state=State.PRESENT,
            evidence_id="evidence_03",
        ),
    ]

    ordered = sort_and_number_steps(input_steps)

    assert len(ordered) == 5
    assert [s.step_no for s in ordered] == [1, 2, 3, 4, 5]

    # Check phase order
    assert ordered[0].phase == Phase.FINDING
    assert ordered[1].phase == Phase.FINDING
    assert ordered[2].phase == Phase.REMEDIATION
    assert ordered[3].phase == Phase.REMEDIATION
    assert ordered[4].phase == Phase.VERIFICATION

    # Check finding operation order
    assert ordered[0].operation == "REPORT_REMAINING_RECORD"
    assert ordered[1].operation == "REPORT_EXPOSED_PII"

    # Check remediation operation order
    assert ordered[2].operation == "DISABLE_DATA_FLOW"
    assert ordered[3].operation == "DELETE_RECORD"


def test_orchestrator_mock_pipeline_run(tmp_path: Path, sample_deletion_request: DeletionRequest, non_deletion_request: DeletionRequest):
    out_file = tmp_path / "test_pipeline_output.csv"

    bundle = DatasetBundle()
    bundle.requests[sample_deletion_request.case_id] = sample_deletion_request
    bundle.requests[non_deletion_request.case_id] = non_deletion_request

    config = AppConfig(
        project_root=tmp_path,
        dataset_dir=tmp_path,
        output_path=out_file,
        sample_requests_path=tmp_path / "sample.csv",
        sample_output_path=tmp_path / "sample_out.csv",
        deletion_requests_path=tmp_path / "del.csv",
        user_identities_path=tmp_path / "uid.csv",
        user_audit_log_path=tmp_path / "aud.csv",
        system_activity_path=tmp_path / "act.csv",
        deletion_rules_path=tmp_path / "rules.csv",
        evidence_manifest_path=tmp_path / "ev.csv",
        evidence_dir=tmp_path / "evidence",
        log_file_path=tmp_path / "log.txt",
    )

    orchestrator = Orchestrator(
        config=config,
        load_dataset_fn=lambda _: bundle,
    )

    results = orchestrator.run(
        dataset_dir=tmp_path,
        output_path=out_file,
        validate=True,
    )

    assert len(results) == 2
    # Ensure non-deletion request is NOT_APPLICABLE with empty steps
    non_del_row = next(r for r in results if r.case_id == non_deletion_request.case_id)
    assert non_del_row.deletion_status == DeletionStatus.NOT_APPLICABLE
    assert non_del_row.steps_json == []

    # Ensure output.csv passed validation
    assert validate_output(out_file, expected_rows=2) is True
