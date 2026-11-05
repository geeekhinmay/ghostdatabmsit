"""Unit tests for code.output.writer and code.output.validator."""

import csv
import json
from pathlib import Path
import pytest

from code.models.enums import DeletionStatus, Phase, State
from code.models.schemas import OutputRow, Step
from code.output.validator import validate_output, validate_steps_json
from code.output.writer import serialize_steps, write_output


def test_serialize_steps():
    steps = [
        Step(
            step_no=1,
            phase=Phase.VERIFICATION,
            system_id="account_service",
            resource_id="acc_1",
            operation="VERIFY_RECORD_ABSENT",
            state=State.ABSENT,
            evidence_id="evidence_54",
        )
    ]
    serialized = serialize_steps(steps)
    parsed = json.loads(serialized)
    assert len(parsed) == 1
    assert parsed[0]["step_no"] == 1
    assert parsed[0]["operation"] == "VERIFY_RECORD_ABSENT"


def test_write_and_validate_output(tmp_path: Path):
    out_file = tmp_path / "output.csv"

    rows = [
        OutputRow(
            case_id="case_02",
            deletion_status=DeletionStatus.NOT_APPLICABLE,
            steps_json=[],
        ),
        OutputRow(
            case_id="case_01",
            deletion_status=DeletionStatus.COMPLETE,
            steps_json=[
                Step(
                    step_no=1,
                    phase=Phase.VERIFICATION,
                    system_id="account_service",
                    resource_id="account_001",
                    operation="VERIFY_RECORD_ABSENT",
                    state=State.ABSENT,
                    evidence_id="evidence_54",
                )
            ],
        ),
    ]

    write_output(rows, out_file)

    # Check file exists and rows are sorted by case_id
    with open(out_file, mode="r", encoding="utf-8") as f:
        reader = list(csv.reader(f))
        assert reader[0] == ["case_id", "deletion_status", "steps_json"]
        assert reader[1][0] == "case_01"
        assert reader[2][0] == "case_02"
        assert reader[2][1] == "NOT_APPLICABLE"
        assert reader[2][2] == "[]"

    # Validate output
    is_valid = validate_output(out_file, expected_rows=2)
    assert is_valid is True


def test_validator_detects_phase_order_error():
    case_id = "case_bad_order"
    bad_steps = [
        {
            "step_no": 1,
            "phase": "VERIFICATION",
            "system_id": "account_service",
            "resource_id": "acc_1",
            "operation": "VERIFY_RECORD_ABSENT",
            "state": "ABSENT",
            "evidence_id": "",
        },
        {
            "step_no": 2,
            "phase": "FINDING",
            "system_id": "account_service",
            "resource_id": "acc_1",
            "operation": "REPORT_REMAINING_RECORD",
            "state": "PRESENT",
            "evidence_id": "ev_1",
        },
    ]
    errors = validate_steps_json(case_id, "INCOMPLETE", bad_steps)
    assert any("Phase ordering violation" in err for err in errors)
