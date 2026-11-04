"""
Verification step generation module.

Generates verification checks for both:
1. COMPLETE cases: evidence-backed verification steps proving the current
   state at audit_at (with valid participant-visible evidence_ids).
2. INCOMPLETE cases: future verification steps that must pass after remediation
   (with empty evidence_ids, evidence_id="").

Follows official verification operation order:
1. VERIFY_RECORD_ABSENT
2. VERIFY_RECORD_PRESENT
3. VERIFY_RECORD_REDACTED
4. VERIFY_RECORD_ANONYMIZED
5. VERIFY_DATA_FLOW_DISABLED
6. VERIFY_RESTORE_BLOCKED
followed by system_id and resource_id in ascending order.

Owned by: Member 4 (Hrushikesh)
Module: code/verification/verifier.py
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from code.models.enums import DeletionStatus, StepOperation, StepPhase, StepState
from code.models.schemas import AuditStep, DeletionRequest
from code.policy.models import PolicyDecision


# Canonical operation priority for VERIFICATION phase
VERIFICATION_OP_ORDER: Dict[StepOperation, int] = {
    StepOperation.VERIFY_RECORD_ABSENT: 1,
    StepOperation.VERIFY_RECORD_PRESENT: 2,
    StepOperation.VERIFY_RECORD_REDACTED: 3,
    StepOperation.VERIFY_RECORD_ANONYMIZED: 4,
    StepOperation.VERIFY_DATA_FLOW_DISABLED: 5,
    StepOperation.VERIFY_RESTORE_BLOCKED: 6,
}


# Mapping from remediation operation to corresponding post-remediation verification
REMEDIATION_TO_VERIFICATION_OP: Dict[StepOperation, StepOperation] = {
    StepOperation.DELETE_RECORD: StepOperation.VERIFY_RECORD_ABSENT,
    StepOperation.REDACT_RECORD: StepOperation.VERIFY_RECORD_REDACTED,
    StepOperation.ANONYMIZE_RECORD: StepOperation.VERIFY_RECORD_ANONYMIZED,
    StepOperation.DISABLE_DATA_FLOW: StepOperation.VERIFY_DATA_FLOW_DISABLED,
    StepOperation.BLOCK_RESTORE: StepOperation.VERIFY_RESTORE_BLOCKED,
}

REMEDIATION_TO_VERIFICATION_STATE: Dict[StepOperation, StepState] = {
    StepOperation.DELETE_RECORD: StepState.ABSENT,
    StepOperation.REDACT_RECORD: StepState.REDACTED,
    StepOperation.ANONYMIZE_RECORD: StepState.ANONYMIZED,
    StepOperation.DISABLE_DATA_FLOW: StepState.DISABLED,
    StepOperation.BLOCK_RESTORE: StepState.BLOCKED,
}


def _sort_verification_key(step: AuditStep) -> tuple:
    """Sort key for verification: op priority -> system_id ASC -> resource_id ASC."""
    op_prio = VERIFICATION_OP_ORDER.get(step.operation, 99)
    return (op_prio, step.system_id or "", step.resource_id or "")


def build_verification_steps(
    request: Union[DeletionRequest, Dict[str, Any]],
    investigation: Any,
    policy: Union[PolicyDecision, Dict[str, Any]],
    start_step_no: Optional[int] = None,
) -> List[AuditStep]:
    """
    Public contract: build verification steps for a case.

    Args:
        request: DeletionRequest object or dict.
        investigation: InvestigationResult or dict.
        policy: PolicyDecision object or dict returned by evaluate_policy.
        start_step_no: Optional starting step number. If None, calculated
                       automatically from findings and remediation counts.

    Returns:
        List of AuditStep in VERIFICATION phase.
        Empty list for NOT_APPLICABLE cases.
    """
    # Extract fields from policy
    if isinstance(policy, dict):
        status = policy.get("deletion_status")
        findings = policy.get("findings", [])
        remediation_items = policy.get("remediation_items", [])
        verification_items = policy.get("verification_items", [])
    else:
        status = policy.deletion_status
        findings = policy.findings
        remediation_items = policy.remediation_items
        verification_items = policy.verification_items

    # Non-deletion requests produce NO verification steps
    if status == DeletionStatus.NOT_APPLICABLE:
        return []

    # Determine default starting step number if not provided
    if start_step_no is None:
        if status == DeletionStatus.COMPLETE:
            start_step_no = 1
        else:
            # For INCOMPLETE, follows findings + remediation
            start_step_no = len(findings) + len(remediation_items) + 1

    steps: List[AuditStep] = []
    seen_resources: set = set()

    if status == DeletionStatus.COMPLETE:
        # Case is COMPLETE: generate evidence-backed verification steps
        for item in verification_items:
            system_id = item.get("system_id") or ""
            resource_id = item.get("resource_id") or ""
            operation = item.get("operation")
            state = item.get("state")
            evidence_id = item.get("evidence_id") or ""

            if isinstance(operation, str):
                operation = StepOperation(operation)
            if isinstance(state, str):
                state = StepState(state)

            key = (system_id, resource_id, operation)
            if key in seen_resources:
                continue
            seen_resources.add(key)

            steps.append(
                AuditStep(
                    step_no=0,
                    phase=StepPhase.VERIFICATION,
                    system_id=system_id,
                    resource_id=resource_id,
                    operation=operation,
                    state=state,
                    evidence_id=evidence_id,  # Valid evidence citation
                )
            )

    else:
        # Case is INCOMPLETE: generate future verification checks
        # 1. Verification for each remediated item (post-remediation check)
        for rem in remediation_items:
            system_id = rem.get("system_id") or ""
            resource_id = rem.get("resource_id") or ""
            rem_op = rem.get("operation")

            if isinstance(rem_op, str):
                rem_op = StepOperation(rem_op)

            v_op = REMEDIATION_TO_VERIFICATION_OP.get(
                rem_op, StepOperation.VERIFY_RECORD_ABSENT
            )
            v_state = REMEDIATION_TO_VERIFICATION_STATE.get(
                rem_op, StepState.ABSENT
            )

            key = (system_id, resource_id, v_op)
            if key in seen_resources:
                continue
            seen_resources.add(key)

            steps.append(
                AuditStep(
                    step_no=0,
                    phase=StepPhase.VERIFICATION,
                    system_id=system_id,
                    resource_id=resource_id,
                    operation=v_op,
                    state=v_state,
                    evidence_id="",  # Future verification uses empty evidence_id
                )
            )

        # 2. Also include verification of already-compliant primary account or retained records
        for item in verification_items:
            system_id = item.get("system_id") or ""
            resource_id = item.get("resource_id") or ""
            operation = item.get("operation")
            state = item.get("state")

            if isinstance(operation, str):
                operation = StepOperation(operation)
            if isinstance(state, str):
                state = StepState(state)

            key = (system_id, resource_id, operation)
            if key in seen_resources:
                continue
            seen_resources.add(key)

            # In incomplete cases, all future verification steps use empty evidence_id
            steps.append(
                AuditStep(
                    step_no=0,
                    phase=StepPhase.VERIFICATION,
                    system_id=system_id,
                    resource_id=resource_id,
                    operation=operation,
                    state=state,
                    evidence_id="",
                )
            )

    # Sort strictly by official order
    steps.sort(key=_sort_verification_key)

    # Assign sequential step numbers
    for idx, step in enumerate(steps, start=start_step_no):
        step.step_no = idx

    return steps
