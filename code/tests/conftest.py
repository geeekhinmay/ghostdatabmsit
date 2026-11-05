"""Pytest fixtures for unit and integration testing."""

import sys
from pathlib import Path
import pytest

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from code.models.enums import DeletionStatus, Phase, ReportedStatus, State
from code.models.schemas import (
    DatasetBundle,
    DeletionRequest,
    DeletionRule,
    EvidenceFileManifest,
    IdentityResolution,
    InvestigationFinding,
    InvestigationResult,
    OutputRow,
    PolicyDecision,
    Step,
    UserAuditRecord,
    UserIdentity,
)


@pytest.fixture
def sample_deletion_request() -> DeletionRequest:
    return DeletionRequest(
        case_id="case_001",
        email="alice@example.com",
        requested_at="2026-09-01T10:00:00Z",
        reported_status=ReportedStatus.COMPLETE,
        reported_at="2026-09-02T10:00:00Z",
        audit_at="2026-09-05T10:00:00Z",
        request_text="Please delete my account and all associated personal information permanently.",
    )


@pytest.fixture
def non_deletion_request() -> DeletionRequest:
    return DeletionRequest(
        case_id="case_002",
        email="bob@example.com",
        requested_at="2026-09-01T10:00:00Z",
        reported_status=ReportedStatus.NOT_STARTED,
        reported_at="2026-09-02T10:00:00Z",
        audit_at="2026-09-05T10:00:00Z",
        request_text="I want to export my data to a JSON file. Please send me the download link.",
    )


@pytest.fixture
def mock_dataset_bundle(sample_deletion_request: DeletionRequest) -> DatasetBundle:
    bundle = DatasetBundle()
    bundle.requests[sample_deletion_request.case_id] = sample_deletion_request
    bundle.identities_by_email["alice@example.com"] = UserIdentity(
        user_id="user_123",
        name="Alice Smith",
        email="alice@example.com",
        phone="+1234567890",
        email_hash="hash_alice",
        updated_at="2026-08-01T00:00:00Z",
    )
    bundle.audit_logs_by_user_id["user_123"] = [
        UserAuditRecord(
            audit_id="audit_1",
            user_id="user_123",
            field_name="email",
            old_value="alice.old@example.com",
            new_value="alice@example.com",
            event_time="2026-07-01T00:00:00Z",
        )
    ]
    bundle.rules.append(
        DeletionRule(
            rule_id="rule_01",
            data_category="USER_PROFILE",
            condition="Always",
            required_action="DELETE",
        )
    )
    bundle.manifest["evidence_01"] = EvidenceFileManifest(
        file_id="evidence_01",
        file_path="evidence/logs/audit.log",
        origin="test_service",
        captured_at="2026-09-03T10:00:00Z",
    )
    return bundle
