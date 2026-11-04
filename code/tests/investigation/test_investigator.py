"""
Unit tests for code/investigation/investigator.py

Covers:
- Exact 3-argument signature: investigate_case(request, identity, evidence)
- Return model contract: InvestigationResult
- Primary account detection (PRESENT vs ABSENT)
- Temporal cutoff enforcement (captured_at <= audit_at; captured_at > audit_at ignored)
- Decoy record rejection (other users' data not attached)
- Discovered records across databases, indexes, support, analytics, exports
- Active data flows detection (InvestigatedDataFlow)
- Restore risks detection (InvestigatedRestoreRisk)
- Retention of security audit log records
- Incomplete case evidence_id clearing on primary account verification
- Complete case evidence citation preservation
- Evidence citations compilation

Owned by: Member 3 (Chirag Gowda)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from code.identity.models import IdentityResolution
from code.investigation import (
    InvestigatedDataFlow,
    InvestigatedResource,
    InvestigatedRestoreRisk,
    InvestigationResult,
    investigate_case,
)
from code.investigation.correlator import EvidenceIndexer
from code.investigation.investigator import _INDEXER_CACHE
from code.models.enums import ReportedStatus, StepState
from code.models.schemas import DeletionRequest, SystemActivity


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _make_request(
    case_id: str = "case_01",
    email: str = "user1@example.com",
    requested_at: str = "2026-09-01T10:00:00Z",
    reported_at: str = "2026-09-05T10:00:00Z",
    audit_at: str = "2026-09-10T00:00:00Z",
    request_text: str = "Please delete my account and data.",
    reported_status: ReportedStatus = ReportedStatus.COMPLETE,
) -> DeletionRequest:
    return DeletionRequest(
        case_id=case_id,
        email=email,
        requested_at=_dt(requested_at),
        reported_status=reported_status,
        reported_at=_dt(reported_at),
        audit_at=_dt(audit_at),
        request_text=request_text,
    )


def _make_identity(
    case_id: str = "case_01",
    user_id: str = "user_01",
    email: str = "user1@example.com",
    name: str = "User One",
    phone: str = "+1-555-0001",
    email_hash: str = "hash1",
    all_emails: list[str] | None = None,
) -> IdentityResolution:
    emails = all_emails or [email]
    return IdentityResolution(
        case_id=case_id,
        user_id=user_id,
        current_name=name,
        current_email=email,
        current_phone=phone,
        current_email_hash=email_hash,
        all_emails=emails,
        all_phones=[phone],
        all_email_hashes=[email_hash],
        all_names=[name],
        is_identified=True,
        matched_by="DIRECT_EMAIL",
    )


# ---------------------------------------------------------------------------
# 1. Signature and Return Type Contracts
# ---------------------------------------------------------------------------

class TestInvestigatorContract:

    def test_investigate_case_exact_signature(self, tmp_path):
        req = _make_request()
        ident = _make_identity()

        # Create minimal dummy evidence_files.csv
        manifest = tmp_path / "evidence_files.csv"
        manifest.write_text("file_id,file_path,origin,captured_at\n", encoding="utf-8")

        with patch("code.investigation.investigator._find_dataset_dir", return_value=tmp_path):
            result = investigate_case(req, ident, [])

        assert isinstance(result, InvestigationResult)
        assert result.case_id == "case_01"
        assert result.user_id == "user_01"
        assert isinstance(result.primary_account, InvestigatedResource)
        assert isinstance(result.records, list)
        assert isinstance(result.data_flows, list)
        assert isinstance(result.restore_risks, list)
        assert isinstance(result.evidence_citations, list)

    def test_returns_investigation_result_model(self, tmp_path):
        req = _make_request(case_id="case_test")
        ident = _make_identity(case_id="case_test")

        manifest = tmp_path / "evidence_files.csv"
        manifest.write_text("file_id,file_path,origin,captured_at\n", encoding="utf-8")

        with patch("code.investigation.investigator._find_dataset_dir", return_value=tmp_path):
            res = investigate_case(req, ident, [])

        assert res.case_id == "case_test"
        assert res.primary_account is not None
        assert res.primary_account.system_id == "account_service"


# ---------------------------------------------------------------------------
# 2. Temporal Cutoff Enforcement (captured_at <= audit_at)
# ---------------------------------------------------------------------------

class TestTemporalCutoff:

    def test_evidence_captured_after_audit_at_is_ignored(self, tmp_path):
        """Evidence with captured_at > audit_at must not appear in findings."""
        # audit_at = 2026-09-10
        req = _make_request(audit_at="2026-09-10T00:00:00Z")
        ident = _make_identity(user_id="user_01", email="user1@example.com")

        # Create two evidence files: one before audit_at (2026-09-08) and one after (2026-09-15)
        manifest = tmp_path / "evidence_files.csv"
        manifest.write_text(
            "file_id,file_path,origin,captured_at\n"
            "evidence_early,early.json,account_service,2026-09-08T00:00:00Z\n"
            "evidence_late,late.json,account_service,2026-09-15T00:00:00Z\n",
            encoding="utf-8",
        )

        # Early evidence: export shows search record
        early_data = {
            "service_exports": {
                "search_service": {
                    "queries": [{"resource_id": "search_001", "email": "user1@example.com", "hits": {"total": 1}}]
                }
            }
        }
        (tmp_path / "early.json").write_text(json.dumps(early_data), encoding="utf-8")

        # Late evidence: export shows search record from after audit_at
        late_data = {
            "service_exports": {
                "search_service": {
                    "queries": [{"resource_id": "search_999", "email": "user1@example.com", "hits": {"total": 1}}]
                }
            }
        }
        (tmp_path / "late.json").write_text(json.dumps(late_data), encoding="utf-8")

        # Clear cache for tmp_path
        key = str(tmp_path.resolve())
        _INDEXER_CACHE.pop(key, None)

        with patch("code.investigation.investigator._find_dataset_dir", return_value=tmp_path):
            result = investigate_case(req, ident, [])

        # search_001 should be found, search_999 should NOT be found
        found_resources = [r.resource_id for r in result.records]
        assert "search_001" in found_resources
        assert "search_999" not in found_resources


# ---------------------------------------------------------------------------
# 3. Decoy Rejection (unrelated users excluded)
# ---------------------------------------------------------------------------

class TestDecoyRejection:

    def test_other_users_records_rejected(self, tmp_path):
        """Records belonging to user_99 must not be included for user_01."""
        req = _make_request()
        ident = _make_identity(user_id="user_01", email="user1@example.com")

        manifest = tmp_path / "evidence_files.csv"
        manifest.write_text(
            "file_id,file_path,origin,captured_at\n"
            "evidence_test,export.json,export_bundle,2026-09-05T00:00:00Z\n",
            encoding="utf-8",
        )

        export_data = {
            "service_exports": {
                "search_service": {
                    "queries": [
                        {"resource_id": "search_user1", "email": "user1@example.com", "hits": {"total": 1}},
                        {"resource_id": "search_user99", "email": "decoy@otherdomain.com", "customer_reference": "user_99", "hits": {"total": 1}},
                    ]
                }
            }
        }
        (tmp_path / "export.json").write_text(json.dumps(export_data), encoding="utf-8")

        key = str(tmp_path.resolve())
        _INDEXER_CACHE.pop(key, None)

        with patch("code.investigation.investigator._find_dataset_dir", return_value=tmp_path):
            result = investigate_case(req, ident, [])

        res_ids = [r.resource_id for r in result.records]
        assert "search_user1" in res_ids
        assert "search_user99" not in res_ids


# ---------------------------------------------------------------------------
# 4. Primary Account State Determination
# ---------------------------------------------------------------------------

class TestPrimaryAccountInvestigation:

    def test_account_absent_in_trace_log_marked_absent(self, tmp_path):
        """When lookup trace log has http_status=404, primary_account is ABSENT."""
        req = _make_request()
        ident = _make_identity(user_id="user_01", email="user1@example.com")

        manifest = tmp_path / "evidence_files.csv"
        manifest.write_text(
            "file_id,file_path,origin,captured_at\n"
            "evidence_94,lookup.log,account_service,2026-09-05T00:00:00Z\n",
            encoding="utf-8",
        )

        log_content = (
            "2026-09-05 08:00:00 INFO service=account_service resource_id=account_001 "
            "email=user1@example.com http_status=404 rows=0\n"
        )
        (tmp_path / "lookup.log").write_text(log_content, encoding="utf-8")

        key = str(tmp_path.resolve())
        _INDEXER_CACHE.pop(key, None)

        with patch("code.investigation.investigator._find_dataset_dir", return_value=tmp_path):
            result = investigate_case(req, ident, [])

        assert result.primary_account is not None
        assert result.primary_account.resource_id == "account_001"
        assert result.primary_account.state == StepState.ABSENT

    def test_account_present_in_failover_replica_marked_present(self, tmp_path):
        """When failover replica SQL shows account row, primary_account is PRESENT."""
        req = _make_request()
        ident = _make_identity(user_id="user_01", email="user1@example.com")

        manifest = tmp_path / "evidence_files.csv"
        manifest.write_text(
            "file_id,file_path,origin,captured_at\n"
            "evidence_54,replica.sql,account_service_replica,2026-09-05T00:00:00Z\n",
            encoding="utf-8",
        )

        sql_content = (
            "INSERT INTO accounts (account_id, user_id, email, status) "
            "VALUES ('account_001', 'user_01', 'user1@example.com', 'ACTIVE');\n"
        )
        (tmp_path / "replica.sql").write_text(sql_content, encoding="utf-8")

        key = str(tmp_path.resolve())
        _INDEXER_CACHE.pop(key, None)

        with patch("code.investigation.investigator._find_dataset_dir", return_value=tmp_path):
            result = investigate_case(req, ident, [])

        assert result.primary_account is not None
        assert result.primary_account.resource_id == "account_001"
        assert result.primary_account.state == StepState.PRESENT
        assert result.primary_account.evidence_id == "evidence_54"


# ---------------------------------------------------------------------------
# 5. Data Flow and Restore Risk Investigation
# ---------------------------------------------------------------------------

class TestFlowsAndRestoreRisks:

    def test_active_sync_connector_detected_as_data_flow(self, tmp_path):
        """Active sync connector in service export is reported as InvestigatedDataFlow."""
        req = _make_request()
        ident = _make_identity(user_id="user_01", email="user1@example.com")

        manifest = tmp_path / "evidence_files.csv"
        manifest.write_text(
            "file_id,file_path,origin,captured_at\n"
            "evidence_92,services.json,integration_service,2026-09-05T00:00:00Z\n",
            encoding="utf-8",
        )

        data = {
            "service_exports": {
                "integration_service": {
                    "connectors": [
                        {
                            "resource_id": "data_flow_01",
                            "customer_reference": "user_01",
                            "enabled": True,
                        }
                    ]
                }
            }
        }
        (tmp_path / "services.json").write_text(json.dumps(data), encoding="utf-8")

        key = str(tmp_path.resolve())
        _INDEXER_CACHE.pop(key, None)

        with patch("code.investigation.investigator._find_dataset_dir", return_value=tmp_path):
            result = investigate_case(req, ident, [])

        assert len(result.data_flows) == 1
        flow = result.data_flows[0]
        assert flow.resource_id == "data_flow_01"
        assert flow.is_active is True
        assert flow.state == StepState.ACTIVE
        assert flow.evidence_id == "evidence_92"

    def test_backup_archive_detected_as_restore_risk(self, tmp_path):
        """Backup archive in service export is reported as InvestigatedRestoreRisk."""
        req = _make_request()
        ident = _make_identity(user_id="user_01", email="user1@example.com")

        manifest = tmp_path / "evidence_files.csv"
        manifest.write_text(
            "file_id,file_path,origin,captured_at\n"
            "evidence_92,services.json,backup_service,2026-09-05T00:00:00Z\n",
            encoding="utf-8",
        )

        data = {
            "service_exports": {
                "backup_service": {
                    "archives": [
                        {
                            "resource_id": "backup_01",
                            "customer_reference": "user_01",
                            "restore_allowed": True,
                        }
                    ]
                }
            }
        }
        (tmp_path / "services.json").write_text(json.dumps(data), encoding="utf-8")

        key = str(tmp_path.resolve())
        _INDEXER_CACHE.pop(key, None)

        with patch("code.investigation.investigator._find_dataset_dir", return_value=tmp_path):
            result = investigate_case(req, ident, [])

        assert len(result.restore_risks) == 1
        risk = result.restore_risks[0]
        assert risk.resource_id == "backup_01"
        assert risk.can_restore is True
        assert risk.state == StepState.ACTIVE
        assert risk.evidence_id == "evidence_92"


# ---------------------------------------------------------------------------
# 6. Verification and Incomplete Evidence ID Rules
# ---------------------------------------------------------------------------

class TestVerificationEvidenceRules:

    def test_complete_case_retains_primary_account_evidence_id(self, tmp_path):
        """In a COMPLETE case (no remaining records), primary account verification keeps evidence_id."""
        req = _make_request()
        ident = _make_identity(user_id="user_01", email="user1@example.com")

        manifest = tmp_path / "evidence_files.csv"
        manifest.write_text(
            "file_id,file_path,origin,captured_at\n"
            "evidence_94,lookup.log,account_service,2026-09-05T00:00:00Z\n",
            encoding="utf-8",
        )

        log_content = (
            "2026-09-05 08:00:00 INFO service=account_service resource_id=account_001 "
            "email=user1@example.com http_status=404 rows=0\n"
        )
        (tmp_path / "lookup.log").write_text(log_content, encoding="utf-8")

        key = str(tmp_path.resolve())
        _INDEXER_CACHE.pop(key, None)

        with patch("code.investigation.investigator._find_dataset_dir", return_value=tmp_path):
            result = investigate_case(req, ident, [])

        # No violations => COMPLETE => primary account retains evidence_id
        assert result.primary_account.state == StepState.ABSENT
        assert result.primary_account.evidence_id == "evidence_94"

    def test_incomplete_case_clears_verified_primary_account_evidence_id(self, tmp_path):
        """In an INCOMPLETE case, primary account verification has evidence_id=''."""
        req = _make_request()
        ident = _make_identity(user_id="user_01", email="user1@example.com")

        manifest = tmp_path / "evidence_files.csv"
        manifest.write_text(
            "file_id,file_path,origin,captured_at\n"
            "evidence_94,lookup.log,account_service,2026-09-05T00:00:00Z\n"
            "evidence_57,search.sql,search_service,2026-09-05T00:00:00Z\n",
            encoding="utf-8",
        )

        # Primary account is absent
        log_content = (
            "2026-09-05 08:00:00 INFO service=account_service resource_id=account_001 "
            "email=user1@example.com http_status=404 rows=0\n"
        )
        (tmp_path / "lookup.log").write_text(log_content, encoding="utf-8")

        # But search record still present => INCOMPLETE case!
        sql_content = (
            "INSERT INTO search_index (search_id, email, query) "
            "VALUES ('search_01', 'user1@example.com', 'orders');\n"
        )
        (tmp_path / "search.sql").write_text(sql_content, encoding="utf-8")

        key = str(tmp_path.resolve())
        _INDEXER_CACHE.pop(key, None)

        with patch("code.investigation.investigator._find_dataset_dir", return_value=tmp_path):
            result = investigate_case(req, ident, [])

        # Because search_01 is PRESENT => has_violations is True => primary account evidence_id cleared
        assert result.primary_account.state == StepState.ABSENT
        assert result.primary_account.evidence_id == ""
