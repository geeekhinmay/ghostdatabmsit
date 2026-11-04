"""Output validator module for verifying submission compliance of output.csv.

Checks header, row count, sorting, JSON validity, step numbering,
phase order, operation order, state coherence, and evidence citation rules.
"""

from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path
from typing import Any

from code.models.enums import (
    ALLOWED_OPERATION_STATES,
    OPERATION_ORDER,
    PHASE_ALLOWED_OPERATIONS,
    PHASE_ORDER,
    DeletionStatus,
    Phase,
)

logger = logging.getLogger(__name__)


def case_sort_key(case_id: str) -> tuple[str, int, str]:
    """Natural sorting key for case identifiers."""
    prefix = re.split(r"\d+", case_id)[0]
    nums = re.findall(r"\d+", case_id)
    num = int(nums[0]) if nums else 0
    return (prefix, num, case_id)


def validate_steps_json(case_id: str, deletion_status: str, steps_data: list[dict[str, Any]]) -> list[str]:
    """Validate steps JSON data against official rules. Returns list of error messages."""
    errors: list[str] = []

    if deletion_status == DeletionStatus.NOT_APPLICABLE.value:
        if steps_data:
            errors.append(f"{case_id}: NOT_APPLICABLE cases must have empty steps_json '[]', found {len(steps_data)} steps")
        return errors

    if deletion_status == DeletionStatus.COMPLETE.value:
        for s in steps_data:
            if s.get("phase") != Phase.VERIFICATION.value:
                errors.append(f"{case_id}: COMPLETE case cannot have '{s.get('phase')}' phase; only VERIFICATION allowed")
            if not s.get("evidence_id"):
                errors.append(f"{case_id}: Step {s.get('step_no')} in COMPLETE case must cite evidence_id, got empty")

    expected_step_no = 1
    prev_phase_rank = 0
    prev_op_rank = 0
    prev_system_id = ""
    prev_resource_id = ""

    for s in steps_data:
        step_no = s.get("step_no")
        phase_str = s.get("phase")
        op_str = s.get("operation")
        state_str = s.get("state")
        sys_id = s.get("system_id", "")
        res_id = s.get("resource_id", "")
        evidence_id = s.get("evidence_id", "")

        # 1. Consecutive numbering starting at 1
        if step_no != expected_step_no:
            errors.append(f"{case_id}: Step numbers must be consecutive starting at 1; expected {expected_step_no}, got {step_no}")
        expected_step_no += 1

        # 2. Phase valid
        try:
            phase = Phase(phase_str)
        except ValueError:
            errors.append(f"{case_id}: Invalid phase '{phase_str}' in step {step_no}")
            continue

        # 3. Operation allowed in phase
        allowed_ops = PHASE_ALLOWED_OPERATIONS.get(phase, set())
        if op_str not in allowed_ops:
            errors.append(f"{case_id}: Operation '{op_str}' is not allowed in phase '{phase_str}' in step {step_no}")

        # 4. State matches operation
        expected_state = ALLOWED_OPERATION_STATES.get(op_str)
        if expected_state and state_str != expected_state.value:
            errors.append(
                f"{case_id}: State '{state_str}' does not match operation '{op_str}' in step {step_no}; expected '{expected_state.value}'"
            )

        # 5. Remediation evidence_id must be empty
        if phase == Phase.REMEDIATION and evidence_id != "":
            errors.append(f"{case_id}: Remediation step {step_no} must have empty evidence_id, got '{evidence_id}'")

        # 6. Sorting rules:
        # Phase order: FINDING (1) -> REMEDIATION (2) -> VERIFICATION (3)
        curr_phase_rank = PHASE_ORDER.get(phase, 99)
        if curr_phase_rank < prev_phase_rank:
            errors.append(f"{case_id}: Phase ordering violation at step {step_no}: '{phase_str}' appeared after a later phase")
        elif curr_phase_rank > prev_phase_rank:
            # Entering new phase, reset within-phase trackers
            prev_phase_rank = curr_phase_rank
            prev_op_rank = OPERATION_ORDER.get(op_str, 99)
            prev_system_id = sys_id
            prev_resource_id = res_id
        else:
            # Same phase: check operation order
            curr_op_rank = OPERATION_ORDER.get(op_str, 99)
            if curr_op_rank < prev_op_rank:
                errors.append(f"{case_id}: Operation ordering violation at step {step_no}: '{op_str}' appeared after a later operation in phase '{phase_str}'")
            elif curr_op_rank > prev_op_rank:
                prev_op_rank = curr_op_rank
                prev_system_id = sys_id
                prev_resource_id = res_id
            else:
                # Same operation: check system_id, then resource_id ascending
                if (sys_id, res_id) < (prev_system_id, prev_resource_id):
                    errors.append(
                        f"{case_id}: Resource ordering violation at step {step_no}: ('{sys_id}', '{res_id}') appeared after ('{prev_system_id}', '{prev_resource_id}')"
                    )
                prev_system_id = sys_id
                prev_resource_id = res_id

    return errors


def validate_output(output_path: str | Path, expected_rows: int | None = None) -> bool:
    """Validate output CSV against official challenge requirements.

    Args:
        output_path: Path to the output.csv file.
        expected_rows: Expected number of data rows (e.g. 518 or 32). If None, check skipped.

    Returns:
        True if the file satisfies all checks, False otherwise.
    """
    path = Path(output_path).resolve()
    if not path.is_file():
        logger.error(f"Output file does not exist: {path}")
        return False

    all_errors: list[str] = []

    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            logger.error("Output file is empty.")
            return False

        expected_header = ["case_id", "deletion_status", "steps_json"]
        if header != expected_header:
            all_errors.append(f"Header mismatch: expected {expected_header}, got {header}")

        rows = list(reader)

    if expected_rows is not None and len(rows) != expected_rows:
        all_errors.append(f"Row count mismatch: expected {expected_rows} data rows, got {len(rows)}")

    seen_case_ids: set[str] = set()
    prev_case_id: str = ""

    valid_statuses = {s.value for s in DeletionStatus}

    for row_idx, row in enumerate(rows, start=2):
        if len(row) != 3:
            all_errors.append(f"Row {row_idx}: expected 3 columns, got {len(row)}")
            continue

        case_id, status_val, steps_json_str = row[0].strip(), row[1].strip(), row[2].strip()

        # Check case_id uniqueness and sorting
        if case_id in seen_case_ids:
            all_errors.append(f"Row {row_idx}: duplicate case_id '{case_id}'")
        seen_case_ids.add(case_id)

        curr_key = case_sort_key(case_id)
        if prev_case_id and curr_key < case_sort_key(prev_case_id):
            all_errors.append(f"Row {row_idx}: case_id out of order: '{case_id}' after '{prev_case_id}'")
        prev_case_id = case_id

        # Check status
        if status_val not in valid_statuses:
            all_errors.append(f"Row {row_idx} ({case_id}): invalid deletion_status '{status_val}'")

        # Check JSON parsing
        try:
            steps_data = json.loads(steps_json_str)
        except json.JSONDecodeError as e:
            all_errors.append(f"Row {row_idx} ({case_id}): malformed steps_json: {e}")
            continue

        if not isinstance(steps_data, list):
            all_errors.append(f"Row {row_idx} ({case_id}): steps_json must be a JSON array, got {type(steps_data).__name__}")
            continue

        # Validate step rules
        step_errors = validate_steps_json(case_id, status_val, steps_data)
        all_errors.extend(step_errors)

    if all_errors:
        for err in all_errors[:20]:
            logger.error(err)
        if len(all_errors) > 20:
            logger.error(f"... and {len(all_errors) - 20} more errors.")
        return False

    return True
