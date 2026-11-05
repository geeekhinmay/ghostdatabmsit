"""
Sample alignment and end-to-end integration tests for Member 3 modules.

Verifies:
- Identity resolution across all 32 sample cases (100% identified)
- Historical email resolution on sample cases (e.g. case_10)
- Temporal boundaries and evidence citation validity
- Primary account state resolution (ABSENT vs PRESENT)
- Discovered records, active data flows, and backup restore risks
- Integration compatibility with policy evaluator, remediation planner, and verifier

Owned by: Member 3 (Chirag Gowda)
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from code.identity import IdentityResolution, resolve_identity
from code.investigation import (
    InvestigatedDataFlow,
    InvestigatedResource,
    InvestigatedRestoreRisk,
    InvestigationResult,
    investigate_case,
)
from code.models.enums import DeletionStatus, StepOperation, StepPhase, StepState


def _find_dataset_dir() -> Optional[Path]:
    """Find the official dataset directory if available."""
    env_dir = os.environ.get("DATASET_DIR")
    if env_dir and Path(env_dir).exists():
        return Path(env_dir)
    for cand in [
        Path("../official_repo/dataset"),
        Path("official_repo/dataset"),
        Path("dataset"),
    ]:
        if cand.exists() and (cand / "sample_output.csv").exists():
            return cand
    return None


DATASET_DIR = _find_dataset_dir()


@pytest.fixture(scope="module")
def dataset_bundle():
    """Load the dataset bundle once for sample alignment tests."""
    if not DATASET_DIR:
        pytest.skip("Official dataset not found in workspace; skipping sample alignment tests")
    from code.ingestion.loader import load_dataset
    return load_dataset(DATASET_DIR)


@pytest.fixture(scope="module")
def sample_outputs() -> Dict[str, Any]:
    """Load sample_output.csv ground truth rows."""
    if not DATASET_DIR:
        pytest.skip("Official dataset not found in workspace")
    with open(DATASET_DIR / "sample_output.csv", encoding="utf-8-sig") as f:
        return {r["case_id"]: r for r in csv.DictReader(f)}


# ---------------------------------------------------------------------------
# 1. Identity Resolution Alignment on 32 Sample Cases
# ---------------------------------------------------------------------------

class TestSampleIdentityResolution:

    def test_all_32_sample_requests_identified(self, dataset_bundle):
        """Every sample request must resolve to an identified user identity."""
        sample_requests = dataset_bundle.sample_requests
        assert len(sample_requests) == 32

        unidentified = []
        for req in sample_requests:
            res = resolve_identity(req, dataset_bundle)
            assert isinstance(res, IdentityResolution)
            if not res.is_identified:
                unidentified.append(req.case_id)

        assert unidentified == [], f"Unidentified cases: {unidentified}"

    def test_historical_email_resolution_sample_cases(self, dataset_bundle):
        """Historical email cases (e.g. case_10, case_29, case_30) resolve via audit log."""
        # Find request for case_10 (nadia.ionescu@yahoo.com)
        req_10 = next((r for r in dataset_bundle.sample_requests if r.case_id == "case_10"), None)
        assert req_10 is not None

        res = resolve_identity(req_10, dataset_bundle)
        assert res.is_identified is True
        assert res.matched_by == "HISTORICAL_EMAIL"
        assert res.user_id == "user_10"
        assert "nadia.ionescu@yahoo.com" in res.all_emails

    def test_identity_clusters_populated(self, dataset_bundle):
        """Identity cluster lists (all_emails, all_phones, etc.) are non-empty for identified users."""
        for req in dataset_bundle.sample_requests:
            res = resolve_identity(req, dataset_bundle)
            assert len(res.all_emails) >= 1
            assert res.case_id == req.case_id


# ---------------------------------------------------------------------------
# 2. Case Investigation Output Contracts on Sample Cases
# ---------------------------------------------------------------------------

class TestSampleCaseInvestigation:

    def test_investigate_case_produces_valid_result(self, dataset_bundle):
        """investigate_case returns typed InvestigationResult for each sample case."""
        for req in dataset_bundle.sample_requests[:10]:
            ident = resolve_identity(req, dataset_bundle)
            inv = investigate_case(req, ident, dataset_bundle)

            assert isinstance(inv, InvestigationResult)
            assert inv.case_id == req.case_id
            assert inv.primary_account is not None
            assert inv.primary_account.system_id == "account_service"
            assert isinstance(inv.records, list)
            assert isinstance(inv.data_flows, list)
            assert isinstance(inv.restore_risks, list)
            assert isinstance(inv.evidence_citations, list)

    def test_temporal_filter_holds_for_all_investigations(self, dataset_bundle):
        """No cited evidence file in any sample case investigation can have captured_at > audit_at."""
        manifest_by_id = dataset_bundle.manifest_by_file_id

        for req in dataset_bundle.sample_requests:
            ident = resolve_identity(req, dataset_bundle)
            inv = investigate_case(req, ident, dataset_bundle)

            for ev_id in inv.evidence_citations:
                if ev_id in manifest_by_id:
                    entry = manifest_by_id[ev_id]
                    cap_t = entry.captured_at
                    assert cap_t <= req.audit_at, (
                        f"Case {req.case_id}: Evidence {ev_id} captured at {cap_t} "
                        f"exceeds audit cutoff {req.audit_at}"
                    )

    def test_complete_cases_have_absent_primary_account(self, dataset_bundle, sample_outputs):
        """Cases marked COMPLETE in sample_output have primary_account.state == ABSENT."""
        for req in dataset_bundle.sample_requests:
            gt = sample_outputs[req.case_id]
            if gt["deletion_status"] == "COMPLETE":
                ident = resolve_identity(req, dataset_bundle)
                inv = investigate_case(req, ident, dataset_bundle)
                assert inv.primary_account.state == StepState.ABSENT, (
                    f"Case {req.case_id} expected COMPLETE but primary account state is {inv.primary_account.state}"
                )


# ---------------------------------------------------------------------------
# 3. Downstream Pipeline Compatibility
# ---------------------------------------------------------------------------

class TestDownstreamIntegration:

    def test_policy_evaluator_consumes_investigation_result(self, dataset_bundle):
        """evaluate_policy accepts InvestigationResult directly from investigate_case."""
        from code.policy.evaluator import evaluate_policy

        req = dataset_bundle.sample_requests[0]  # case_01
        ident = resolve_identity(req, dataset_bundle)
        inv = investigate_case(req, ident, dataset_bundle)

        policy_decision = evaluate_policy(req, inv, dataset_bundle.deletion_rules)
        assert policy_decision is not None
        assert policy_decision.case_id == req.case_id

    def test_remediation_and_verifier_consume_investigation(self, dataset_bundle):
        """build_remediation_plan and build_verification_steps consume InvestigationResult."""
        from code.policy.evaluator import evaluate_policy
        from code.remediation.planner import build_remediation_plan
        from code.verification.verifier import build_verification_steps

        req = dataset_bundle.sample_requests[0]  # case_01
        ident = resolve_identity(req, dataset_bundle)
        inv = investigate_case(req, ident, dataset_bundle)
        policy_decision = evaluate_policy(req, inv, dataset_bundle.deletion_rules)

        remediation = build_remediation_plan(req, inv, policy_decision)
        assert isinstance(remediation, list)

        verification = build_verification_steps(req, inv, policy_decision)
        assert isinstance(verification, list)
        assert len(verification) >= 1
