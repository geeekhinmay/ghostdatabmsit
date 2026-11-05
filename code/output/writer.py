"""Output writer module for generating the official output.csv.

Produces the exact official CSV structure with case_id, deletion_status, and steps_json.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Sequence

from code.models.enums import DeletionStatus
from code.models.schemas import OutputRow, Step


def case_sort_key(case_id: str) -> tuple[str, int, str]:
    """Natural sorting key for case identifiers (e.g. case_33 before case_100)."""
    prefix = re.split(r"\d+", case_id)[0]
    nums = re.findall(r"\d+", case_id)
    num = int(nums[0]) if nums else 0
    return (prefix, num, case_id)


def serialize_steps(steps: Sequence[Step]) -> str:
    """Serialize a sequence of Step objects into the required JSON array string."""
    steps_dicts = [
        {
            "step_no": s.step_no,
            "phase": s.phase.value if hasattr(s.phase, "value") else str(s.phase),
            "system_id": s.system_id,
            "resource_id": s.resource_id,
            "operation": s.operation,
            "state": s.state.value if hasattr(s.state, "value") else str(s.state),
            "evidence_id": s.evidence_id,
        }
        for s in steps
    ]
    return json.dumps(steps_dicts, separators=(",", ":"))


def write_output(results: Sequence[OutputRow], output_path: str | Path) -> None:
    """Write the final audited results to output.csv.

    Args:
        results: Sequence of OutputRow objects, one per audited case.
        output_path: Target path for the output CSV file.
    """
    path = Path(output_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Sort results by case_id using natural sort to satisfy official ordering requirement
    sorted_results = sorted(results, key=lambda r: case_sort_key(r.case_id))

    with open(path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(["case_id", "deletion_status", "steps_json"])

        for row in sorted_results:
            status_val = row.deletion_status.value if isinstance(row.deletion_status, DeletionStatus) else str(row.deletion_status)
            if status_val == DeletionStatus.NOT_APPLICABLE.value:
                steps_str = "[]"
            else:
                steps_str = serialize_steps(row.steps_json)

            writer.writerow([row.case_id, status_val, steps_str])
