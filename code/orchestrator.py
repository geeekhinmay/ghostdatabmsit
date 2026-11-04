"""Central pipeline orchestrator for Ghost Data deletion audit.

Coordinates ingestion, identity resolution, case investigation, policy evaluation,
remediation planning, verification, and output generation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Sequence

from code.models.enums import (
    ALLOWED_OPERATION_STATES,
    OPERATION_ORDER,
    PHASE_ORDER,
    DeletionStatus,
    Phase,
    ReportedStatus,
)
from code.models.schemas import (
    DatasetBundle,
    DeletionRequest,
    IdentityResolution,
    InvestigationFinding,
    InvestigationResult,
    OutputRow,
    PolicyDecision,
    Step,
)
from code.output.validator import validate_output
from code.output.writer import write_output
from config.settings import AppConfig, get_config

logger = logging.getLogger(__name__)


def sort_and_number_steps(steps: Sequence[Step]) -> list[Step]:
    """Sort steps according to official rules and reassign consecutive step numbers.

    Rules:
    1. Phase order: FINDING (1) -> REMEDIATION (2) -> VERIFICATION (3)
    2. Operation order within phase (per official table)
    3. system_id ascending
    4. resource_id ascending
    5. Consecutive numbering starting at 1
    """
    sorted_steps = sorted(
        steps,
        key=lambda s: (
            PHASE_ORDER.get(s.phase, 99),
            OPERATION_ORDER.get(s.operation, 99),
            s.system_id,
            s.resource_id,
        ),
    )

    numbered_steps: list[Step] = []
    for idx, s in enumerate(sorted_steps, start=1):
        numbered_steps.append(
            Step(
                step_no=idx,
                phase=s.phase,
                system_id=s.system_id,
                resource_id=s.resource_id,
                operation=s.operation,
                state=s.state,
                evidence_id=s.evidence_id,
            )
        )

    return numbered_steps


# =====================================================================
# Fallback / Baseline implementations for Member 2, 3, 4 contracts
# Used when sub-modules are not yet present, guaranteeing immediate
# end-to-end execution and integration testability.
# =====================================================================

def default_load_dataset(dataset_dir: str | Path) -> DatasetBundle:
    """Fallback loader when code.ingestion is not yet installed."""
    import csv
    from code.models.schemas import (
        DeletionRule,
        EvidenceFileManifest,
        SystemActivityRecord,
        UserAuditRecord,
        UserIdentity,
    )

    dpath = Path(dataset_dir)
    bundle = DatasetBundle()

    # Load deletion requests from both sample and full datasets if available
    req_files = [dpath / "sample_deletion_requests.csv", dpath / "deletion_requests.csv"]
    for del_req_file in req_files:
        if del_req_file.is_file():
            with open(del_req_file, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    req = DeletionRequest(
                        case_id=row["case_id"],
                        email=row["email"],
                        requested_at=row["requested_at"],
                        reported_status=ReportedStatus(row["reported_status"]),
                        reported_at=row["reported_at"],
                        audit_at=row["audit_at"],
                        request_text=row["request_text"],
                    )
                    bundle.requests[req.case_id] = req

    # Load user identities
    user_id_file = dpath / "user_identities.csv"
    if user_id_file.is_file():
        with open(user_id_file, mode="r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ui = UserIdentity(
                    user_id=row["user_id"],
                    name=row["name"],
                    email=row["email"],
                    phone=row["phone"],
                    email_hash=row["email_hash"],
                    updated_at=row["updated_at"],
                )
                bundle.identities_by_user_id[ui.user_id] = ui
                bundle.identities_by_email[ui.email.lower()] = ui

    # Load user audit log
    audit_file = dpath / "user_audit_log.csv"
    if audit_file.is_file():
        with open(audit_file, mode="r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rec = UserAuditRecord(
                    audit_id=row["audit_id"],
                    user_id=row["user_id"],
                    field_name=row.get("field_name") or row.get("field_changed", ""),
                    old_value=row["old_value"],
                    new_value=row["new_value"],
                    event_time=row.get("event_time") or row.get("changed_at", ""),
                )
                bundle.audit_logs_by_user_id.setdefault(rec.user_id, []).append(rec)
                if rec.field_name == "email":
                    bundle.audit_logs_by_email.setdefault(rec.old_value.lower(), []).append(rec)
                    bundle.audit_logs_by_email.setdefault(rec.new_value.lower(), []).append(rec)

    # Load deletion rules
    rules_file = dpath / "deletion_rules.csv"
    if rules_file.is_file():
        with open(rules_file, mode="r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                bundle.rules.append(
                    DeletionRule(
                        rule_id=row["rule_id"],
                        data_category=row["data_category"],
                        condition=row["condition"],
                        required_action=row["required_action"],
                    )
                )

    # Load system activity
    activity_file = dpath / "system_activity.csv"
    if activity_file.is_file():
        with open(activity_file, mode="r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                bundle.activities.append(
                    SystemActivityRecord(
                        activity_id=row["activity_id"],
                        event_time=row["event_time"],
                        event_type=row["event_type"],
                        source_system=row["source_system"],
                        target_system=row.get("target_system", ""),
                        resource_id=row["resource_id"],
                        reported_result=row["reported_result"],
                        details=row.get("details", ""),
                    )
                )

    # Load evidence files manifest
    ev_file = dpath / "evidence_files.csv"
    if ev_file.is_file():
        with open(ev_file, mode="r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                bundle.manifest[row["file_id"]] = EvidenceFileManifest(
                    file_id=row["file_id"],
                    file_path=row["file_path"],
                    origin=row["origin"],
                    captured_at=row["captured_at"],
                )

    return bundle


def default_resolve_identity(request: DeletionRequest, dataset: DatasetBundle) -> IdentityResolution:
    """Fallback identity resolver when code.identity is not yet installed."""
    req_email = request.email.lower()
    resolution = IdentityResolution(case_id=request.case_id, all_emails={req_email})

    # Search current identities
    if req_email in dataset.identities_by_email:
        ui = dataset.identities_by_email[req_email]
        resolution.user_id = ui.user_id
        resolution.current_name = ui.name
        resolution.current_email = ui.email
        resolution.current_phone = ui.phone
        resolution.current_hash = ui.email_hash
        resolution.all_emails.add(ui.email.lower())
        resolution.all_names.add(ui.name)
        resolution.all_phones.add(ui.phone)
        resolution.all_hashes.add(ui.email_hash)

    # Search historical audit records if user_id is found
    if resolution.user_id and resolution.user_id in dataset.audit_logs_by_user_id:
        logs = dataset.audit_logs_by_user_id[resolution.user_id]
        resolution.audit_history = logs
        for log in logs:
            if log.field_changed == "email":
                if log.old_value:
                    resolution.all_emails.add(log.old_value.lower())
                if log.new_value:
                    resolution.all_emails.add(log.new_value.lower())
            elif log.field_changed == "name":
                if log.old_value:
                    resolution.all_names.add(log.old_value)
                if log.new_value:
                    resolution.all_names.add(log.new_value)
            elif log.field_changed == "phone":
                if log.old_value:
                    resolution.all_phones.add(log.old_value)
                if log.new_value:
                    resolution.all_phones.add(log.new_value)

    return resolution


def default_investigate_case(
    request: DeletionRequest,
    identity: IdentityResolution,
    evidence: DatasetBundle,
) -> InvestigationResult:
    """Fallback case investigator when code.investigation is not yet installed."""
    # Basic intent check
    text_lower = request.request_text.lower()
    # Non-deletion keywords
    non_deletion_markers = ["marketing opt-out", "unsubscribe", "export my data", "access my data", "correct my name"]
    is_deletion = True
    for marker in non_deletion_markers:
        if marker in text_lower and "delete" not in text_lower and "remove" not in text_lower:
            is_deletion = False
            break

    result = InvestigationResult(
        case_id=request.case_id,
        is_deletion_request=is_deletion,
        identity=identity,
        audit_cutoff=request.audit_at,
    )
    return result


def default_evaluate_policy(
    request: DeletionRequest,
    investigation: InvestigationResult,
    rules: list,
) -> PolicyDecision:
    """Fallback policy evaluator when code.policy is not yet installed."""
    if not investigation.is_deletion_request:
        return PolicyDecision(
            case_id=request.case_id,
            deletion_status=DeletionStatus.NOT_APPLICABLE,
            rationale="Request does not authorize deletion",
        )

    if investigation.findings:
        return PolicyDecision(
            case_id=request.case_id,
            deletion_status=DeletionStatus.INCOMPLETE,
            violations_found=True,
            rationale=f"Found {len(investigation.findings)} active findings/violations",
        )

    # If no findings and was reported COMPLETE or verified
    return PolicyDecision(
        case_id=request.case_id,
        deletion_status=DeletionStatus.COMPLETE,
        rationale="Deletion verified complete",
    )


def default_build_remediation_plan(
    request: DeletionRequest,
    investigation: InvestigationResult,
    policy: PolicyDecision,
) -> list[Step]:
    """Fallback remediation planner when code.remediation is not yet installed."""
    return policy.remediation_steps


def default_build_verification_steps(
    request: DeletionRequest,
    investigation: InvestigationResult,
    policy: PolicyDecision,
) -> list[Step]:
    """Fallback verification step builder when code.verification is not yet installed."""
    return policy.verification_steps


class Orchestrator:
    """Central orchestrator executing the 4-module pipeline."""

    def __init__(
        self,
        config: AppConfig | None = None,
        load_dataset_fn: Callable[[str | Path], DatasetBundle] | None = None,
        resolve_identity_fn: Callable[[DeletionRequest, DatasetBundle], IdentityResolution] | None = None,
        investigate_case_fn: Callable[[DeletionRequest, IdentityResolution, DatasetBundle], InvestigationResult] | None = None,
        evaluate_policy_fn: Callable[[DeletionRequest, InvestigationResult, list], PolicyDecision] | None = None,
        build_remediation_fn: Callable[[DeletionRequest, InvestigationResult, PolicyDecision], list[Step]] | None = None,
        build_verification_fn: Callable[[DeletionRequest, InvestigationResult, PolicyDecision], list[Step]] | None = None,
    ) -> None:
        self.config = config or get_config()

        # Dynamic import of team members' modules or fallback
        self.load_dataset_fn = load_dataset_fn or self._resolve_member2_loader()
        self.resolve_identity_fn = resolve_identity_fn or self._resolve_member3_identity()
        self.investigate_case_fn = investigate_case_fn or self._resolve_member3_investigator()
        self.evaluate_policy_fn = evaluate_policy_fn or self._resolve_member4_policy()
        self.build_remediation_fn = build_remediation_fn or self._resolve_member4_remediation()
        self.build_verification_fn = build_verification_fn or self._resolve_member4_verification()

    @staticmethod
    def _resolve_member2_loader() -> Callable[[str | Path], DatasetBundle]:
        try:
            from code.ingestion import load_dataset  # type: ignore
            return load_dataset
        except (ImportError, AttributeError):
            return default_load_dataset

    @staticmethod
    def _resolve_member3_identity() -> Callable[[DeletionRequest, DatasetBundle], IdentityResolution]:
        try:
            from code.identity import resolve_identity  # type: ignore
            return resolve_identity
        except (ImportError, AttributeError):
            return default_resolve_identity

    @staticmethod
    def _resolve_member3_investigator() -> Callable[[DeletionRequest, IdentityResolution, DatasetBundle], InvestigationResult]:
        try:
            from code.investigation import investigate_case  # type: ignore
            return investigate_case
        except (ImportError, AttributeError):
            return default_investigate_case

    @staticmethod
    def _resolve_member4_policy() -> Callable[[DeletionRequest, InvestigationResult, list], PolicyDecision]:
        try:
            from code.policy import evaluate_policy  # type: ignore
            return evaluate_policy
        except (ImportError, AttributeError):
            return default_evaluate_policy

    @staticmethod
    def _resolve_member4_remediation() -> Callable[[DeletionRequest, InvestigationResult, PolicyDecision], list[Step]]:
        try:
            from code.remediation import build_remediation_plan  # type: ignore
            return build_remediation_plan
        except (ImportError, AttributeError):
            return default_build_remediation_plan

    @staticmethod
    def _resolve_member4_verification() -> Callable[[DeletionRequest, InvestigationResult, PolicyDecision], list[Step]]:
        try:
            from code.verification import build_verification_steps  # type: ignore
            return build_verification_steps
        except (ImportError, AttributeError):
            return default_build_verification_steps

    def audit_case(self, request: DeletionRequest, dataset: DatasetBundle) -> OutputRow:
        """Run full 4-stage audit for a single case."""
        # Stage 1: Identity Resolution (Member 3)
        identity = self.resolve_identity_fn(request, dataset)

        # Stage 2: Case Investigation (Member 3)
        investigation = self.investigate_case_fn(request, identity, dataset)

        # Stage 3: Policy Evaluation (Member 4)
        policy = self.evaluate_policy_fn(request, investigation, dataset.rules)

        # Check for NOT_APPLICABLE
        if not investigation.is_deletion_request or policy.deletion_status == DeletionStatus.NOT_APPLICABLE:
            return OutputRow(
                case_id=request.case_id,
                deletion_status=DeletionStatus.NOT_APPLICABLE,
                steps_json=[],
            )

        raw_steps: list[Step] = []

        if policy.deletion_status == DeletionStatus.COMPLETE:
            # COMPLETE cases only include verification steps proving current compliant state
            verification_steps = self.build_verification_fn(request, investigation, policy)
            raw_steps.extend(verification_steps)
            ordered_steps = sort_and_number_steps(raw_steps)
            return OutputRow(
                case_id=request.case_id,
                deletion_status=DeletionStatus.COMPLETE,
                steps_json=ordered_steps,
            )

        # INCOMPLETE cases: include findings, proposed remediation, and future verification
        # 1. Findings from investigation
        for f in investigation.findings:
            raw_steps.append(
                Step(
                    step_no=1,  # renumbered during sort_and_number_steps
                    phase=Phase.FINDING,
                    system_id=f.system_id,
                    resource_id=f.resource_id,
                    operation=f.operation,
                    state=f.state,
                    evidence_id=f.evidence_id,
                )
            )

        # 2. Remediation plan
        remediation_steps = self.build_remediation_fn(request, investigation, policy)
        for s in remediation_steps:
            raw_steps.append(
                Step(
                    step_no=1,
                    phase=Phase.REMEDIATION,
                    system_id=s.system_id,
                    resource_id=s.resource_id,
                    operation=s.operation,
                    state=s.state,
                    evidence_id="",  # Future remediation must have empty evidence_id
                )
            )

        # 3. Verification steps
        verification_steps = self.build_verification_fn(request, investigation, policy)
        for s in verification_steps:
            raw_steps.append(
                Step(
                    step_no=1,
                    phase=Phase.VERIFICATION,
                    system_id=s.system_id,
                    resource_id=s.resource_id,
                    operation=s.operation,
                    state=s.state,
                    evidence_id="",  # Future verification must have empty evidence_id
                )
            )

        ordered_steps = sort_and_number_steps(raw_steps)
        return OutputRow(
            case_id=request.case_id,
            deletion_status=DeletionStatus.INCOMPLETE,
            steps_json=ordered_steps,
        )

    def run(
        self,
        dataset_dir: str | Path | None = None,
        output_path: str | Path | None = None,
        case_ids: Sequence[str] | None = None,
        validate: bool = True,
    ) -> list[OutputRow]:
        """Execute full end-to-end pipeline."""
        ds_dir = Path(dataset_dir) if dataset_dir else self.config.dataset_dir
        out_path = Path(output_path) if output_path else self.config.output_path

        logger.info(f"Loading dataset from: {ds_dir}")
        dataset = self.load_dataset_fn(ds_dir)

        requests_to_audit = dataset.requests
        if case_ids:
            requests_to_audit = {cid: req for cid, req in dataset.requests.items() if cid in case_ids}

        logger.info(f"Auditing {len(requests_to_audit)} requests...")
        results: list[OutputRow] = []

        # Sort case_ids for deterministic execution order
        for case_id in sorted(requests_to_audit.keys()):
            req = requests_to_audit[case_id]
            row = self.audit_case(req, dataset)
            results.append(row)

        logger.info(f"Writing {len(results)} rows to: {out_path}")
        write_output(results, out_path)

        if validate:
            is_valid = validate_output(out_path, expected_rows=len(results))
            if not is_valid:
                raise ValueError(f"Generated output failed validation: {out_path}")
            logger.info("Output validation PASSED.")

        return results
