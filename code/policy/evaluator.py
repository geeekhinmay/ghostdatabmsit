"""
Policy evaluation engine.

Evaluates an investigated case against deletion_rules.csv policy,
determines case status (COMPLETE, INCOMPLETE, or NOT_APPLICABLE),
and produces ordered findings.

Owned by: Member 4 (Hrushikesh)
Module: code/policy/evaluator.py
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from code.models.enums import (
    DeletionStatus,
    RequiredAction,
    StepOperation,
    StepPhase,
    StepState,
)
from code.models.schemas import AuditStep, DeletionRequest, DeletionRule
from code.policy.intent import classify_request_intent
from code.policy.models import PolicyDecision
from code.policy.rules import infer_data_category, resolve_rule_for_record


# Canonical operation priority for FINDING phase
FINDING_OP_ORDER: Dict[StepOperation, int] = {
    StepOperation.REPORT_REMAINING_RECORD: 1,
    StepOperation.REPORT_EXPOSED_PII: 2,
    StepOperation.REPORT_ACTIVE_DATA_FLOW: 3,
    StepOperation.REPORT_RESTORE_RISK: 4,
}


def _get_field(obj: Any, name: str, default: Any = None) -> Any:
    """Helper to get a field from either a Pydantic model or a dictionary."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _sort_findings_key(step: AuditStep) -> tuple:
    """Sort key for findings: op priority -> system_id ASC -> resource_id ASC."""
    op_prio = FINDING_OP_ORDER.get(step.operation, 99)
    return (op_prio, step.system_id or "", step.resource_id or "")


def evaluate_policy(
    request: Union[DeletionRequest, Dict[str, Any]],
    investigation: Any,
    rules: Any,
) -> PolicyDecision:
    """
    Public contract: evaluate deletion policy on a request and its investigation.

    Args:
        request: DeletionRequest object or dict containing request_text and case_id.
        investigation: InvestigationResult or dict containing discovered records,
                       flows, and backup risks.
        rules: Optional list or dict of DeletionRule objects from deletion_rules.csv.

    Returns:
        PolicyDecision with deletion_status, ordered findings, and action items.
    """
    case_id = _get_field(request, "case_id", "case_unknown")
    request_text = _get_field(request, "request_text", "")

    # 1. Check whether request actually authorises deletion
    is_deletion, reason = classify_request_intent(request_text)
    if not is_deletion:
        return PolicyDecision(
            case_id=case_id,
            is_deletion_request=False,
            deletion_status=DeletionStatus.NOT_APPLICABLE,
            non_deletion_reason=reason,
            findings=[],
            remediation_items=[],
            verification_items=[],
            treatment_by_resource={},
            details={"intent_check": "NOT_APPLICABLE", "reason": reason},
        )

    # 2. Extract items from investigation
    records = _get_field(investigation, "records", []) or []
    data_flows = _get_field(investigation, "data_flows", []) or []
    restore_risks = _get_field(investigation, "restore_risks", []) or []
    primary_account = _get_field(investigation, "primary_account", None)

    findings: List[AuditStep] = []
    remediation_items: List[Dict[str, Any]] = []
    verification_items: List[Dict[str, Any]] = []
    treatment_by_resource: Dict[str, RequiredAction] = {}

    # Track seen resources to avoid duplicate findings
    seen_resources: set = set()

    # Combine records with primary_account if provided separately
    all_records = list(records)
    if primary_account is not None and primary_account not in all_records:
        all_records.insert(0, primary_account)

    # 3. Evaluate each record against deletion_rules.csv
    for rec in all_records:
        system_id = _get_field(rec, "system_id") or "account_service"
        resource_id = _get_field(rec, "resource_id") or ""
        evidence_id = _get_field(rec, "evidence_id") or ""
        state = _get_field(rec, "state") or _get_field(rec, "status") or "PRESENT"

        if isinstance(state, str):
            state_upper = state.upper()
        else:
            state_upper = state.value if hasattr(state, "value") else str(state).upper()

        if resource_id:
            seen_resources.add(resource_id)

        # Resolve policy rule
        rule = resolve_rule_for_record(rec, rules)
        action = rule.required_action
        treatment_by_resource[resource_id] = action

        # Evaluate compliance based on required action
        if action == RequiredAction.DELETE:
            if state_upper in ["PRESENT", "ACTIVE", "EXISTS"]:
                # VIOLATION: Record should have been deleted
                findings.append(
                    AuditStep(
                        step_no=0,
                        phase=StepPhase.FINDING,
                        system_id=system_id,
                        resource_id=resource_id,
                        operation=StepOperation.REPORT_REMAINING_RECORD,
                        state=StepState.PRESENT,
                        evidence_id=evidence_id,
                    )
                )
                remediation_items.append(
                    {
                        "system_id": system_id,
                        "resource_id": resource_id,
                        "operation": StepOperation.DELETE_RECORD,
                        "state": StepState.ABSENT,
                        "evidence_id": "",
                    }
                )
            else:
                # COMPLIANT: Record is already deleted/absent
                verification_items.append(
                    {
                        "system_id": system_id,
                        "resource_id": resource_id,
                        "operation": StepOperation.VERIFY_RECORD_ABSENT,
                        "state": StepState.ABSENT,
                        "evidence_id": evidence_id,
                        "is_primary": (system_id == "account_service"),
                    }
                )

        elif action == RequiredAction.REDACT:
            # Check if PII is still exposed
            has_exposed_pii = _get_field(rec, "has_exposed_pii", None)
            if has_exposed_pii is None:
                # Infer from state: if state is REDACTED, then compliant; otherwise exposed
                has_exposed_pii = state_upper != "REDACTED"

            if has_exposed_pii or state_upper in ["PRESENT", "ACTIVE", "EXPOSED"]:
                # VIOLATION: Exposed PII
                findings.append(
                    AuditStep(
                        step_no=0,
                        phase=StepPhase.FINDING,
                        system_id=system_id,
                        resource_id=resource_id,
                        operation=StepOperation.REPORT_EXPOSED_PII,
                        state=StepState.PRESENT,
                        evidence_id=evidence_id,
                    )
                )
                remediation_items.append(
                    {
                        "system_id": system_id,
                        "resource_id": resource_id,
                        "operation": StepOperation.REDACT_RECORD,
                        "state": StepState.REDACTED,
                        "evidence_id": "",
                    }
                )
            else:
                # COMPLIANT: Already redacted
                verification_items.append(
                    {
                        "system_id": system_id,
                        "resource_id": resource_id,
                        "operation": StepOperation.VERIFY_RECORD_REDACTED,
                        "state": StepState.REDACTED,
                        "evidence_id": evidence_id,
                    }
                )

        elif action == RequiredAction.ANONYMIZE:
            # Check if attributable to user
            is_attributable = _get_field(rec, "is_attributable", None)
            if is_attributable is None:
                is_attributable = state_upper != "ANONYMIZED"

            if is_attributable or state_upper in ["PRESENT", "ACTIVE", "EXPOSED"]:
                # VIOLATION: Analytics profile still attributable
                findings.append(
                    AuditStep(
                        step_no=0,
                        phase=StepPhase.FINDING,
                        system_id=system_id,
                        resource_id=resource_id,
                        operation=StepOperation.REPORT_EXPOSED_PII,
                        state=StepState.PRESENT,
                        evidence_id=evidence_id,
                    )
                )
                remediation_items.append(
                    {
                        "system_id": system_id,
                        "resource_id": resource_id,
                        "operation": StepOperation.ANONYMIZE_RECORD,
                        "state": StepState.ANONYMIZED,
                        "evidence_id": "",
                    }
                )
            else:
                # COMPLIANT: Already anonymized
                verification_items.append(
                    {
                        "system_id": system_id,
                        "resource_id": resource_id,
                        "operation": StepOperation.VERIFY_RECORD_ANONYMIZED,
                        "state": StepState.ANONYMIZED,
                        "evidence_id": evidence_id,
                    }
                )

        elif action == RequiredAction.RETAIN:
            # Retained records must remain PRESENT
            treatment_by_resource[resource_id] = RequiredAction.RETAIN
            verification_items.append(
                {
                    "system_id": system_id,
                    "resource_id": resource_id,
                    "operation": StepOperation.VERIFY_RECORD_PRESENT,
                    "state": StepState.PRESENT,
                    "evidence_id": evidence_id,
                    "is_retained": True,
                }
            )

    # 4. Evaluate data flows (active replication, sync, connectors)
    for flow in data_flows:
        flow_sys = _get_field(flow, "system_id") or "integration_service"
        flow_res = _get_field(flow, "resource_id") or ""
        flow_ev = _get_field(flow, "evidence_id") or ""
        is_active = _get_field(flow, "is_active", None)
        flow_state = _get_field(flow, "state") or "ACTIVE"

        if is_active is None:
            is_active = str(flow_state).upper() in ["ACTIVE", "ENABLED", "RUNNING"]

        if is_active:
            # VIOLATION: Active sync/flow
            findings.append(
                AuditStep(
                    step_no=0,
                    phase=StepPhase.FINDING,
                    system_id=flow_sys,
                    resource_id=flow_res,
                    operation=StepOperation.REPORT_ACTIVE_DATA_FLOW,
                    state=StepState.ACTIVE,
                    evidence_id=flow_ev,
                )
            )
            remediation_items.append(
                {
                    "system_id": flow_sys,
                    "resource_id": flow_res,
                    "operation": StepOperation.DISABLE_DATA_FLOW,
                    "state": StepState.DISABLED,
                    "evidence_id": "",
                }
            )
        else:
            # COMPLIANT: Data flow is disabled
            verification_items.append(
                {
                    "system_id": flow_sys,
                    "resource_id": flow_res,
                    "operation": StepOperation.VERIFY_DATA_FLOW_DISABLED,
                    "state": StepState.DISABLED,
                    "evidence_id": flow_ev,
                }
            )

    # 5. Evaluate restore risks (backup archives that can restore data)
    for risk in restore_risks:
        risk_sys = _get_field(risk, "system_id") or "backup_service"
        risk_res = _get_field(risk, "resource_id") or ""
        risk_ev = _get_field(risk, "evidence_id") or ""
        can_restore = _get_field(risk, "can_restore", None)
        is_blocked = _get_field(risk, "is_blocked", None)
        risk_state = _get_field(risk, "state") or "ACTIVE"

        if is_blocked is not None:
            has_restore_risk = not is_blocked
        elif can_restore is not None:
            has_restore_risk = can_restore
        else:
            has_restore_risk = str(risk_state).upper() in ["ACTIVE", "UNBLOCKED", "RISK"]

        if has_restore_risk:
            # VIOLATION: Restore path is active
            findings.append(
                AuditStep(
                    step_no=0,
                    phase=StepPhase.FINDING,
                    system_id=risk_sys,
                    resource_id=risk_res,
                    operation=StepOperation.REPORT_RESTORE_RISK,
                    state=StepState.ACTIVE,
                    evidence_id=risk_ev,
                )
            )
            remediation_items.append(
                {
                    "system_id": risk_sys,
                    "resource_id": risk_res,
                    "operation": StepOperation.BLOCK_RESTORE,
                    "state": StepState.BLOCKED,
                    "evidence_id": "",
                }
            )
        else:
            # COMPLIANT: Restore is blocked
            verification_items.append(
                {
                    "system_id": risk_sys,
                    "resource_id": risk_res,
                    "operation": StepOperation.VERIFY_RESTORE_BLOCKED,
                    "state": StepState.BLOCKED,
                    "evidence_id": risk_ev,
                }
            )

    # 6. Determine final deletion status
    if len(findings) > 0:
        status = DeletionStatus.INCOMPLETE
    else:
        status = DeletionStatus.COMPLETE

    # 7. Sort findings according to official ordering rules
    findings.sort(key=_sort_findings_key)

    # Assign sequential step numbers to findings
    for idx, f in enumerate(findings, start=1):
        f.step_no = idx

    return PolicyDecision(
        case_id=case_id,
        is_deletion_request=True,
        deletion_status=status,
        findings=findings,
        remediation_items=remediation_items,
        verification_items=verification_items,
        treatment_by_resource=treatment_by_resource,
        details={
            "violation_count": len(findings),
            "remediation_count": len(remediation_items),
            "verification_count": len(verification_items),
        },
    )
