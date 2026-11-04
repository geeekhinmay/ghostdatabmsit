"""
Remediation planning module.

Generates the ordered remediation plan for incomplete deletion cases,
respecting system dependencies (disabling active data flows and blocking
restore risks before altering records) and following the official ordering:
1. DISABLE_DATA_FLOW
2. BLOCK_RESTORE
3. DELETE_RECORD
4. REDACT_RECORD
5. ANONYMIZE_RECORD
followed by system_id and resource_id in ascending order.

Owned by: Member 4 (Hrushikesh)
Module: code/remediation/planner.py
"""

from __future__ import annotations

from typing import Any, Dict, List, Union

from code.models.enums import DeletionStatus, StepOperation, StepPhase, StepState
from code.models.schemas import AuditStep, DeletionRequest
from code.policy.models import PolicyDecision


# Canonical operation priority for REMEDIATION phase
REMEDIATION_OP_ORDER: Dict[StepOperation, int] = {
    StepOperation.DISABLE_DATA_FLOW: 1,
    StepOperation.BLOCK_RESTORE: 2,
    StepOperation.DELETE_RECORD: 3,
    StepOperation.REDACT_RECORD: 4,
    StepOperation.ANONYMIZE_RECORD: 5,
}


def _sort_remediation_key(step: AuditStep) -> tuple:
    """Sort key for remediation: op priority -> system_id ASC -> resource_id ASC."""
    op_prio = REMEDIATION_OP_ORDER.get(step.operation, 99)
    return (op_prio, step.system_id or "", step.resource_id or "")


def build_remediation_plan(
    request: Union[DeletionRequest, Dict[str, Any]],
    investigation: Any,
    policy: Union[PolicyDecision, Dict[str, Any]],
    start_step_no: int = 1,
) -> List[AuditStep]:
    """
    Public contract: build an ordered remediation plan for an investigated case.

    Args:
        request: DeletionRequest object or dict.
        investigation: InvestigationResult or dict.
        policy: PolicyDecision object or dict returned by evaluate_policy.
        start_step_no: Step number to start from (defaults to 1 if standalone,
                       or consecutive after findings if integrated).

    Returns:
        List of AuditStep in REMEDIATION phase with evidence_id="".
        Empty list for COMPLETE or NOT_APPLICABLE cases.
    """
    # Check deletion status
    if isinstance(policy, dict):
        status = policy.get("deletion_status")
        findings = policy.get("findings", [])
        items = policy.get("remediation_items", [])
    else:
        status = policy.deletion_status
        findings = policy.findings
        items = policy.remediation_items

    # Only INCOMPLETE cases produce remediation steps
    if status != DeletionStatus.INCOMPLETE:
        return []

    # If start_step_no is 1 but policy has findings, offset automatically
    if start_step_no == 1 and len(findings) > 0:
        start_step_no = len(findings) + 1

    steps: List[AuditStep] = []

    # Build remediation steps from policy remediation items
    for item in items:
        system_id = item.get("system_id") or ""
        resource_id = item.get("resource_id") or ""
        operation = item.get("operation")
        state = item.get("state")

        if isinstance(operation, str):
            operation = StepOperation(operation)
        if isinstance(state, str):
            state = StepState(state)

        steps.append(
            AuditStep(
                step_no=0,
                phase=StepPhase.REMEDIATION,
                system_id=system_id,
                resource_id=resource_id,
                operation=operation,
                state=state,
                evidence_id="",  # Proposed remediation uses empty evidence_id
            )
        )

    # Sort strictly according to official ordering
    steps.sort(key=_sort_remediation_key)

    # Number consecutively
    for idx, step in enumerate(steps, start=start_step_no):
        step.step_no = idx

    return steps
