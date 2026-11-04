"""
Unit tests for code.ingestion.loader (load_dataset).

Tests cover:
  - Normal load with all CSV files present
  - Missing individual files (graceful empty list)
  - Malformed rows (skipped, rest loaded)
  - Index building (requests_by_case_id, identities_by_email, etc.)
  - Email normalisation (uppercase input → lowercase index)
  - Invalid dataset_dir raises ValueError

All tests use temporary directories with mock CSV data.  No real dataset
files are required; this module is self-contained.

Run with:
    python -m pytest code/tests/ingestion/test_loader.py -v

Owned by: Member 2 — Chinmay Motagi
"""

import csv
import tempfile
from pathlib import Path

import pytest

from code.ingestion.loader import load_dataset
from code.models.enums import ReportedStatus, RequiredAction
from code.models.schemas import DatasetBundle


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DELETION_REQUESTS_HEADER = "case_id,email,requested_at,reported_status,reported_at,audit_at,request_text"
DELETION_REQUESTS_ROW = (
    "case_01,alice@example.com,2026-09-01T00:00:00Z,COMPLETE,"
    "2026-09-02T00:00:00Z,2026-09-03T00:00:00Z,Please delete my data"
)

USER_IDENTITIES_HEADER = "user_id,name,email,phone,email_hash,updated_at"
_HASH_64 = "a" * 64
USER_IDENTITIES_ROW = f"user_01,Alice Smith,alice@example.com,+1 555 000 0001,{_HASH_64},2026-01-01T00:00:00Z"

USER_AUDIT_LOG_HEADER = "audit_id,user_id,event_time,field_name,old_value,new_value"
USER_AUDIT_LOG_ROW = "audit_01,user_01,2026-01-15T10:00:00Z,email,old@example.com,alice@example.com"

SYSTEM_ACTIVITY_HEADER = "activity_id,event_time,event_type,source_system,target_system,resource_id,reported_result,details"
SYSTEM_ACTIVITY_ROW = "activity_01,2026-09-01T12:00:00Z,DELETE_RECORD,account_service,archive_service,account_001,SUCCESS,Deleted account_001"

DELETION_RULES_HEADER = "rule_id,data_category,condition,required_action"
DELETION_RULES_ROW = "rule_01,USER_PROFILE,Always,DELETE"

EVIDENCE_MANIFEST_HEADER = "file_id,file_path,origin,captured_at"
EVIDENCE_MANIFEST_ROW = "evidence_01,evidence/logs/test.log,central_observability,2026-09-15T12:00:00Z"

SAMPLE_DELETION_REQUESTS_ROW = (
    "case_s01,bob@example.com,2026-08-01T00:00:00Z,NOT_STARTED,"
    "2026-08-02T00:00:00Z,2026-08-03T00:00:00Z,I want my data removed"
)


def _write_csv(path: Path, header: str, *rows: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(header + "\n")
        for row in rows:
            f.write(row + "\n")


def _make_dataset_dir(tmp_path: Path, **overrides) -> Path:
    """
    Create a minimal mock dataset directory with one valid row per CSV.
    Pass keyword arguments to override or omit specific files.

    override key → CSV content string (use None to skip creating the file).
    """
    files = {
        "deletion_requests.csv": f"{DELETION_REQUESTS_HEADER}\n{DELETION_REQUESTS_ROW}\n",
        "sample_deletion_requests.csv": f"{DELETION_REQUESTS_HEADER}\n{SAMPLE_DELETION_REQUESTS_ROW}\n",
        "user_identities.csv": f"{USER_IDENTITIES_HEADER}\n{USER_IDENTITIES_ROW}\n",
        "user_audit_log.csv": f"{USER_AUDIT_LOG_HEADER}\n{USER_AUDIT_LOG_ROW}\n",
        "system_activity.csv": f"{SYSTEM_ACTIVITY_HEADER}\n{SYSTEM_ACTIVITY_ROW}\n",
        "deletion_rules.csv": f"{DELETION_RULES_HEADER}\n{DELETION_RULES_ROW}\n",
        "evidence_files.csv": f"{EVIDENCE_MANIFEST_HEADER}\n{EVIDENCE_MANIFEST_ROW}\n",
    }
    files.update(overrides)
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    for name, content in files.items():
        if content is not None:
            (dataset_dir / name).write_text(content, encoding="utf-8")
    return dataset_dir


# ---------------------------------------------------------------------------
# Normal-case tests
# ---------------------------------------------------------------------------


class TestLoadDatasetNormal:
    def test_returns_dataset_bundle(self, tmp_path):
        ds = _make_dataset_dir(tmp_path)
        bundle = load_dataset(ds)
        assert isinstance(bundle, DatasetBundle)

    def test_deletion_requests_count(self, tmp_path):
        ds = _make_dataset_dir(tmp_path)
        bundle = load_dataset(ds)
        assert len(bundle.deletion_requests) == 1
        assert bundle.deletion_requests[0].case_id == "case_01"

    def test_sample_requests_loaded(self, tmp_path):
        ds = _make_dataset_dir(tmp_path)
        bundle = load_dataset(ds)
        assert len(bundle.sample_requests) == 1
        assert bundle.sample_requests[0].case_id == "case_s01"

    def test_user_identities_count(self, tmp_path):
        ds = _make_dataset_dir(tmp_path)
        bundle = load_dataset(ds)
        assert len(bundle.user_identities) == 1
        assert bundle.user_identities[0].user_id == "user_01"

    def test_user_audit_log_count(self, tmp_path):
        ds = _make_dataset_dir(tmp_path)
        bundle = load_dataset(ds)
        assert len(bundle.user_audit_log) == 1
        assert bundle.user_audit_log[0].audit_id == "audit_01"

    def test_system_activity_count(self, tmp_path):
        ds = _make_dataset_dir(tmp_path)
        bundle = load_dataset(ds)
        assert len(bundle.system_activity) == 1
        assert bundle.system_activity[0].activity_id == "activity_01"

    def test_deletion_rules_count(self, tmp_path):
        ds = _make_dataset_dir(tmp_path)
        bundle = load_dataset(ds)
        assert len(bundle.deletion_rules) == 1
        assert bundle.deletion_rules[0].required_action == RequiredAction.DELETE

    def test_evidence_manifest_count(self, tmp_path):
        ds = _make_dataset_dir(tmp_path)
        bundle = load_dataset(ds)
        assert len(bundle.evidence_manifest) == 1
        assert bundle.evidence_manifest[0].file_id == "evidence_01"

    def test_accepts_path_string(self, tmp_path):
        ds = _make_dataset_dir(tmp_path)
        bundle = load_dataset(str(ds))
        assert len(bundle.deletion_requests) == 1

    def test_accepts_path_object(self, tmp_path):
        ds = _make_dataset_dir(tmp_path)
        bundle = load_dataset(Path(ds))
        assert len(bundle.deletion_requests) == 1


# ---------------------------------------------------------------------------
# Index-building tests
# ---------------------------------------------------------------------------


class TestIndexBuilding:
    def test_requests_by_case_id(self, tmp_path):
        ds = _make_dataset_dir(tmp_path)
        bundle = load_dataset(ds)
        assert "case_01" in bundle.requests_by_case_id
        assert bundle.requests_by_case_id["case_01"].email == "alice@example.com"

    def test_identities_by_user_id(self, tmp_path):
        ds = _make_dataset_dir(tmp_path)
        bundle = load_dataset(ds)
        assert "user_01" in bundle.identities_by_user_id
        assert bundle.identities_by_user_id["user_01"].name == "Alice Smith"

    def test_identities_by_email(self, tmp_path):
        ds = _make_dataset_dir(tmp_path)
        bundle = load_dataset(ds)
        assert "alice@example.com" in bundle.identities_by_email

    def test_rules_by_category(self, tmp_path):
        ds = _make_dataset_dir(tmp_path)
        bundle = load_dataset(ds)
        assert "USER_PROFILE" in bundle.rules_by_category
        assert bundle.rules_by_category["USER_PROFILE"].rule_id == "rule_01"

    def test_manifest_by_file_id(self, tmp_path):
        ds = _make_dataset_dir(tmp_path)
        bundle = load_dataset(ds)
        assert "evidence_01" in bundle.manifest_by_file_id

    def test_activity_by_id(self, tmp_path):
        ds = _make_dataset_dir(tmp_path)
        bundle = load_dataset(ds)
        assert "activity_01" in bundle.activity_by_id

    def test_audit_by_id(self, tmp_path):
        ds = _make_dataset_dir(tmp_path)
        bundle = load_dataset(ds)
        assert "audit_01" in bundle.audit_by_id


# ---------------------------------------------------------------------------
# Email normalisation tests
# ---------------------------------------------------------------------------


class TestEmailNormalisation:
    def test_uppercase_email_in_request_normalised(self, tmp_path):
        row = (
            "case_02,ALICE@EXAMPLE.COM,2026-09-01T00:00:00Z,COMPLETE,"
            "2026-09-02T00:00:00Z,2026-09-03T00:00:00Z,Delete my data"
        )
        ds = _make_dataset_dir(
            tmp_path,
            **{"deletion_requests.csv": f"{DELETION_REQUESTS_HEADER}\n{row}\n"}
        )
        bundle = load_dataset(ds)
        assert bundle.deletion_requests[0].email == "alice@example.com"

    def test_uppercase_email_in_identity_normalised_in_index(self, tmp_path):
        row = f"user_02,Bob Jones,BOB@EXAMPLE.COM,+1 555 000 0002,{'b' * 64},2026-01-01T00:00:00Z"
        ds = _make_dataset_dir(
            tmp_path,
            **{"user_identities.csv": f"{USER_IDENTITIES_HEADER}\n{row}\n"}
        )
        bundle = load_dataset(ds)
        assert "bob@example.com" in bundle.identities_by_email


# ---------------------------------------------------------------------------
# Missing-file tests
# ---------------------------------------------------------------------------


class TestMissingFiles:
    def test_missing_deletion_requests_returns_empty(self, tmp_path):
        ds = _make_dataset_dir(tmp_path, **{"deletion_requests.csv": None})
        bundle = load_dataset(ds)
        assert bundle.deletion_requests == []

    def test_missing_user_identities_returns_empty(self, tmp_path):
        ds = _make_dataset_dir(tmp_path, **{"user_identities.csv": None})
        bundle = load_dataset(ds)
        assert bundle.user_identities == []

    def test_missing_evidence_manifest_returns_empty(self, tmp_path):
        ds = _make_dataset_dir(tmp_path, **{"evidence_files.csv": None})
        bundle = load_dataset(ds)
        assert bundle.evidence_manifest == []

    def test_missing_all_files_returns_empty_bundle(self, tmp_path):
        empty_dir = tmp_path / "empty_dataset"
        empty_dir.mkdir()
        bundle = load_dataset(empty_dir)
        assert bundle.deletion_requests == []
        assert bundle.user_identities == []
        assert bundle.deletion_rules == []


# ---------------------------------------------------------------------------
# Malformed-row tests
# ---------------------------------------------------------------------------


class TestMalformedRows:
    def test_malformed_request_row_skipped(self, tmp_path):
        """A row with an invalid reported_status is skipped; valid rows still load."""
        good_row = DELETION_REQUESTS_ROW
        bad_row = "case_bad,bad@example.com,NOT_A_DATE,INVALID_STATUS,2026-09-02T00:00:00Z,2026-09-03T00:00:00Z,text"
        content = f"{DELETION_REQUESTS_HEADER}\n{good_row}\n{bad_row}\n"
        ds = _make_dataset_dir(tmp_path, **{"deletion_requests.csv": content})
        bundle = load_dataset(ds)
        # At least the good row should load
        assert any(r.case_id == "case_01" for r in bundle.deletion_requests)

    def test_malformed_rule_skipped(self, tmp_path):
        """A rule with an invalid required_action is skipped."""
        bad_rule = "rule_bad,FAKE_CATEGORY,Always,NOT_A_VALID_ACTION"
        good_rule = DELETION_RULES_ROW
        content = f"{DELETION_RULES_HEADER}\n{good_rule}\n{bad_rule}\n"
        ds = _make_dataset_dir(tmp_path, **{"deletion_rules.csv": content})
        bundle = load_dataset(ds)
        assert any(r.rule_id == "rule_01" for r in bundle.deletion_rules)
        assert all(r.rule_id != "rule_bad" for r in bundle.deletion_rules)

    def test_header_only_csv_returns_empty(self, tmp_path):
        ds = _make_dataset_dir(
            tmp_path,
            **{"deletion_requests.csv": f"{DELETION_REQUESTS_HEADER}\n"}
        )
        bundle = load_dataset(ds)
        assert bundle.deletion_requests == []


# ---------------------------------------------------------------------------
# Error-condition tests
# ---------------------------------------------------------------------------


class TestErrorConditions:
    def test_nonexistent_dir_raises_value_error(self):
        with pytest.raises(ValueError, match="does not exist"):
            load_dataset("/nonexistent/path/that/does/not/exist")

    def test_file_path_raises_value_error(self, tmp_path):
        fake_file = tmp_path / "not_a_dir.csv"
        fake_file.write_text("content")
        with pytest.raises(ValueError):
            load_dataset(fake_file)


# ---------------------------------------------------------------------------
# Multiple-row tests
# ---------------------------------------------------------------------------


class TestMultipleRows:
    def test_multiple_requests_all_loaded(self, tmp_path):
        rows = "\n".join([
            f"case_{i:02d},user{i}@example.com,2026-09-01T00:00:00Z,COMPLETE,"
            f"2026-09-02T00:00:00Z,2026-09-03T00:00:00Z,Delete my data"
            for i in range(1, 6)
        ])
        content = f"{DELETION_REQUESTS_HEADER}\n{rows}\n"
        ds = _make_dataset_dir(tmp_path, **{"deletion_requests.csv": content})
        bundle = load_dataset(ds)
        assert len(bundle.deletion_requests) == 5

    def test_all_reported_statuses_parsed(self, tmp_path):
        rows = [
            "case_01,a@x.com,2026-09-01T00:00:00Z,COMPLETE,2026-09-02T00:00:00Z,2026-09-03T00:00:00Z,text",
            "case_02,b@x.com,2026-09-01T00:00:00Z,PARTIALLY_COMPLETE,2026-09-02T00:00:00Z,2026-09-03T00:00:00Z,text",
            "case_03,c@x.com,2026-09-01T00:00:00Z,NOT_STARTED,2026-09-02T00:00:00Z,2026-09-03T00:00:00Z,text",
        ]
        content = f"{DELETION_REQUESTS_HEADER}\n" + "\n".join(rows) + "\n"
        ds = _make_dataset_dir(tmp_path, **{"deletion_requests.csv": content})
        bundle = load_dataset(ds)
        statuses = {r.case_id: r.reported_status for r in bundle.deletion_requests}
        assert statuses["case_01"] == ReportedStatus.COMPLETE
        assert statuses["case_02"] == ReportedStatus.PARTIALLY_COMPLETE
        assert statuses["case_03"] == ReportedStatus.NOT_STARTED
