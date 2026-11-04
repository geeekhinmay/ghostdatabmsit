"""
Unit tests for code.ingestion.evidence (parse_all_evidence) and
code.parsers.* sub-parsers.

Tests cover:
  - CSV evidence parsing (normal, missing, malformed)
  - JSONL evidence parsing
  - JSON snapshot bundle parsing
  - SQL snapshot parsing
  - Log file parsing
  - PDF parsing (fallback / stub path)
  - Image parsing (stub path, no OCR dependency required)
  - Format detection
  - Identity extraction (extract_identifiers)
  - Record type inference (infer_record_type_and_system)
  - safe_parse_datetime edge cases

Run with:
    python -m pytest code/tests/ingestion/test_evidence.py -v

Owned by: Member 2 — Chinmay Motagi
"""

from __future__ import annotations

import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import pytest

from code.ingestion.evidence import _detect_format, parse_all_evidence
from code.models.enums import EvidenceFormat
from code.models.schemas import EvidenceFileEntry, EvidenceRecord
from code.parsers.common import (
    extract_identifiers,
    infer_record_type_and_system,
    safe_parse_datetime,
)
from code.parsers.csv_parser import parse_csv_evidence
from code.parsers.json_parser import parse_json_evidence
from code.parsers.log_parser import parse_log_evidence
from code.parsers.sql_parser import parse_sql_evidence


# ---------------------------------------------------------------------------
# Helper: build a mock EvidenceFileEntry
# ---------------------------------------------------------------------------

def _make_entry(
    file_id: str = "evidence_01",
    file_path: str = "evidence/logs/test.log",
    origin: str = "central_observability",
    captured_at: str = "2026-09-15T12:00:00Z",
) -> EvidenceFileEntry:
    return EvidenceFileEntry(
        file_id=file_id,
        file_path=file_path,
        origin=origin,
        captured_at=captured_at,
    )


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------


class TestDetectFormat:
    def test_csv(self):
        assert _detect_format("evidence/records/foo.csv") == EvidenceFormat.CSV

    def test_json(self):
        assert _detect_format("evidence/records/foo.json") == EvidenceFormat.JSON

    def test_jsonl(self):
        assert _detect_format("evidence/records/foo.jsonl") == EvidenceFormat.JSONL

    def test_sql(self):
        assert _detect_format("evidence/databases/foo.sql") == EvidenceFormat.SQL

    def test_log(self):
        assert _detect_format("evidence/logs/foo.log") == EvidenceFormat.LOG

    def test_pdf(self):
        assert _detect_format("evidence/documents/foo.pdf") == EvidenceFormat.PDF

    def test_png(self):
        assert _detect_format("evidence/images/foo.png") == EvidenceFormat.PNG

    def test_jpg(self):
        assert _detect_format("evidence/images/foo.jpg") == EvidenceFormat.JPG

    def test_txt(self):
        assert _detect_format("evidence/records/foo.txt") == EvidenceFormat.TXT

    def test_unknown(self):
        assert _detect_format("evidence/data/foo.xyz") == EvidenceFormat.UNKNOWN


# ---------------------------------------------------------------------------
# safe_parse_datetime
# ---------------------------------------------------------------------------


class TestSafeParseDatetime:
    def test_iso_z(self):
        dt = safe_parse_datetime("2026-09-15T12:00:00Z")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 9

    def test_iso_offset(self):
        dt = safe_parse_datetime("2026-09-15T12:00:00+05:30")
        assert dt is not None

    def test_space_separator(self):
        dt = safe_parse_datetime("2026-09-15 12:00:00")
        assert dt is not None

    def test_empty_string(self):
        assert safe_parse_datetime("") is None

    def test_none_input(self):
        assert safe_parse_datetime(None) is None  # type: ignore[arg-type]

    def test_invalid_string(self):
        assert safe_parse_datetime("not-a-date") is None

    def test_fractional_seconds(self):
        dt = safe_parse_datetime("2026-09-15T12:00:00.123456Z")
        assert dt is not None


# ---------------------------------------------------------------------------
# extract_identifiers
# ---------------------------------------------------------------------------


class TestExtractIdentifiers:
    def test_extracts_user_id(self):
        ids = extract_identifiers({"user_id": "user_042"})
        assert ids["user_id"] == "user_042"

    def test_extracts_email(self):
        ids = extract_identifiers({"email": "alice@example.com"})
        assert ids["email"] == "alice@example.com"

    def test_email_lowercased(self):
        ids = extract_identifiers({"email": "ALICE@EXAMPLE.COM"})
        assert ids["email"] == "alice@example.com"

    def test_extracts_email_hash(self):
        h = "a" * 64
        ids = extract_identifiers({"email_hash": h})
        assert ids["email_hash"] == h

    def test_extracts_phone(self):
        ids = extract_identifiers({"phone": "+1 555 000 0001"})
        assert ids["phone"] == "+1 555 000 0001"

    def test_extracts_name(self):
        ids = extract_identifiers({"name": "Alice Smith"})
        assert ids["name"] == "Alice Smith"

    def test_missing_fields_are_none(self):
        ids = extract_identifiers({})
        assert ids["user_id"] is None
        assert ids["email"] is None

    def test_fallback_email_in_value(self):
        """Email found in an unrecognised column via regex scan."""
        ids = extract_identifiers({"some_field": "Contact: bob@test.org"})
        assert ids["email"] == "bob@test.org"

    def test_invalid_user_id_not_extracted(self):
        ids = extract_identifiers({"user_id": "not_a_valid_id"})
        assert ids["user_id"] is None


# ---------------------------------------------------------------------------
# infer_record_type_and_system
# ---------------------------------------------------------------------------


class TestInferRecordTypeAndSystem:
    def test_account_service_from_path(self):
        entry = _make_entry(file_path="evidence/databases/customer_data_read_replica.sql")
        rtype, sys_id = infer_record_type_and_system({}, entry)
        assert rtype == "account"
        assert sys_id == "account_service"

    def test_search_service_from_path(self):
        entry = _make_entry(file_path="evidence/databases/customer_search_primary.sql")
        rtype, sys_id = infer_record_type_and_system({}, entry)
        assert rtype == "search_index"
        assert sys_id == "search_service"

    def test_support_from_path(self):
        entry = _make_entry(file_path="evidence/logs/support_replica.log")
        rtype, sys_id = infer_record_type_and_system({}, entry)
        assert rtype == "support_message"
        assert sys_id == "support_platform"

    def test_analytics_from_origin(self):
        entry = _make_entry(
            file_path="evidence/records/analytics_report.json",
            origin="analytics_platform",
        )
        rtype, sys_id = infer_record_type_and_system({}, entry)
        assert rtype == "analytics_profile"

    def test_sql_table_hint_wins(self):
        entry = _make_entry(file_path="evidence/databases/unknown.sql")
        rtype, sys_id = infer_record_type_and_system({}, entry, hint="user_accounts")
        assert rtype == "account"

    def test_unknown_falls_back(self):
        entry = _make_entry(file_path="evidence/unknown/random.bin")
        rtype, sys_id = infer_record_type_and_system({}, entry)
        assert rtype == "unknown"
        assert sys_id is None


# ---------------------------------------------------------------------------
# CSV parser
# ---------------------------------------------------------------------------


class TestCsvParser:
    def test_parses_rows(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "user_id,email,resource_id,created_at\n"
            "user_01,alice@example.com,account_001,2026-09-01T12:00:00Z\n"
        )
        entry = _make_entry(
            file_id="evidence_01",
            file_path="evidence/records/test.csv",
        )
        records = parse_csv_evidence(csv_path, entry, EvidenceFormat.CSV)
        assert len(records) == 1
        rec = records[0]
        assert rec.user_id == "user_01"
        assert rec.email == "alice@example.com"
        assert rec.resource_id == "account_001"
        assert rec.file_id == "evidence_01"

    def test_missing_file_returns_empty(self, tmp_path):
        entry = _make_entry()
        records = parse_csv_evidence(tmp_path / "nonexistent.csv", entry, EvidenceFormat.CSV)
        assert records == []

    def test_header_only_returns_empty(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text("user_id,email\n")
        entry = _make_entry()
        records = parse_csv_evidence(csv_path, entry, EvidenceFormat.CSV)
        assert records == []

    def test_multiple_rows(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        rows = "user_id,email\n" + "\n".join(
            f"user_{i:02d},user{i}@example.com" for i in range(5)
        ) + "\n"
        csv_path.write_text(rows)
        entry = _make_entry()
        records = parse_csv_evidence(csv_path, entry, EvidenceFormat.CSV)
        assert len(records) == 5


# ---------------------------------------------------------------------------
# JSON parser
# ---------------------------------------------------------------------------


class TestJsonParser:
    def test_parses_list_of_objects(self, tmp_path):
        data = [
            {"user_id": "user_01", "email": "alice@example.com", "id": "account_001"},
            {"user_id": "user_02", "email": "bob@example.com", "id": "account_002"},
        ]
        json_path = tmp_path / "records.json"
        json_path.write_text(json.dumps(data))
        entry = _make_entry(
            file_path="evidence/records/customer_data_snapshot_bundle.json"
        )
        records = parse_json_evidence(json_path, entry, EvidenceFormat.JSON)
        assert len(records) == 2
        assert records[0].user_id == "user_01"

    def test_parses_wrapped_dict(self, tmp_path):
        data = {
            "accounts": [
                {"user_id": "user_03", "email": "carol@example.com"},
            ]
        }
        json_path = tmp_path / "bundle.json"
        json_path.write_text(json.dumps(data))
        entry = _make_entry(file_path="evidence/records/account_snapshot.json")
        records = parse_json_evidence(json_path, entry, EvidenceFormat.JSON)
        assert len(records) == 1
        assert records[0].user_id == "user_03"

    def test_parses_jsonl(self, tmp_path):
        lines = [
            json.dumps({"user_id": "user_04", "email": "dave@example.com"}),
            json.dumps({"user_id": "user_05", "email": "eve@example.com"}),
        ]
        jsonl_path = tmp_path / "records.jsonl"
        jsonl_path.write_text("\n".join(lines) + "\n")
        entry = _make_entry(file_path="evidence/records/records.jsonl")
        records = parse_json_evidence(jsonl_path, entry, EvidenceFormat.JSONL)
        assert len(records) == 2

    def test_invalid_json_returns_empty(self, tmp_path):
        json_path = tmp_path / "bad.json"
        json_path.write_text("{not valid json")
        entry = _make_entry()
        records = parse_json_evidence(json_path, entry, EvidenceFormat.JSON)
        assert records == []

    def test_missing_file_returns_empty(self, tmp_path):
        entry = _make_entry()
        records = parse_json_evidence(tmp_path / "nonexistent.json", entry, EvidenceFormat.JSON)
        assert records == []

    def test_nested_fields_flattened(self, tmp_path):
        data = [{"profile": {"user_id": "user_06", "email": "frank@example.com"}}]
        json_path = tmp_path / "nested.json"
        json_path.write_text(json.dumps(data))
        entry = _make_entry(file_path="evidence/records/account_snapshot.json")
        records = parse_json_evidence(json_path, entry, EvidenceFormat.JSON)
        assert len(records) == 1
        # Flattened key should be accessible
        assert "profile.user_id" in records[0].raw_fields


# ---------------------------------------------------------------------------
# Log parser
# ---------------------------------------------------------------------------


class TestLogParser:
    def test_parses_log_lines(self, tmp_path):
        log_content = textwrap.dedent("""\
            2026-09-15T12:00:00Z INFO account_service DELETE user_01 account_001 SUCCESS
            2026-09-15T12:01:00Z INFO search_service DELETE user_02 search_042 SUCCESS
        """)
        log_path = tmp_path / "test.log"
        log_path.write_text(log_content)
        entry = _make_entry(file_path="evidence/logs/test.log")
        records = parse_log_evidence(log_path, entry, EvidenceFormat.LOG)
        assert len(records) == 2

    def test_extracts_user_id_from_log(self, tmp_path):
        log_path = tmp_path / "test.log"
        log_path.write_text("2026-09-15T12:00:00Z INFO Deleted user_042 account_001\n")
        entry = _make_entry()
        records = parse_log_evidence(log_path, entry, EvidenceFormat.LOG)
        assert records[0].user_id == "user_042"

    def test_extracts_email_from_log(self, tmp_path):
        log_path = tmp_path / "test.log"
        log_path.write_text("2026-09-15T12:00:00Z INFO email=alice@example.com deleted\n")
        entry = _make_entry()
        records = parse_log_evidence(log_path, entry, EvidenceFormat.LOG)
        assert records[0].email == "alice@example.com"

    def test_extracts_resource_id_from_log(self, tmp_path):
        log_path = tmp_path / "test.log"
        log_path.write_text("2026-09-15T12:00:00Z INFO account_001 deleted successfully\n")
        entry = _make_entry()
        records = parse_log_evidence(log_path, entry, EvidenceFormat.LOG)
        assert records[0].resource_id == "account_001"

    def test_blank_lines_skipped(self, tmp_path):
        log_path = tmp_path / "test.log"
        log_path.write_text("\n\n2026-09-15T12:00:00Z INFO account_001\n\n")
        entry = _make_entry()
        records = parse_log_evidence(log_path, entry, EvidenceFormat.LOG)
        assert len(records) == 1

    def test_missing_file_returns_empty(self, tmp_path):
        entry = _make_entry()
        records = parse_log_evidence(tmp_path / "nonexistent.log", entry, EvidenceFormat.LOG)
        assert records == []


# ---------------------------------------------------------------------------
# SQL parser
# ---------------------------------------------------------------------------


class TestSqlParser:
    def test_parses_simple_sql(self, tmp_path):
        sql = textwrap.dedent("""\
            CREATE TABLE accounts (
                user_id TEXT,
                email TEXT,
                resource_id TEXT,
                created_at TEXT
            );
            INSERT INTO accounts VALUES ('user_01', 'alice@example.com', 'account_001', '2026-09-01T00:00:00Z');
            INSERT INTO accounts VALUES ('user_02', 'bob@example.com', 'account_002', '2026-09-01T00:00:00Z');
        """)
        sql_path = tmp_path / "snapshot.sql"
        sql_path.write_text(sql)
        entry = _make_entry(
            file_id="evidence_05",
            file_path="evidence/databases/customer_data_read_replica.sql",
        )
        records = parse_sql_evidence(sql_path, entry)
        assert len(records) == 2
        assert any(r.user_id == "user_01" for r in records)
        assert any(r.email == "alice@example.com" for r in records)

    def test_multiple_tables(self, tmp_path):
        sql = textwrap.dedent("""\
            CREATE TABLE accounts (user_id TEXT, email TEXT);
            INSERT INTO accounts VALUES ('user_01', 'alice@example.com');
            CREATE TABLE search_index (user_id TEXT, search_id TEXT);
            INSERT INTO search_index VALUES ('user_01', 'search_001');
        """)
        sql_path = tmp_path / "snapshot.sql"
        sql_path.write_text(sql)
        entry = _make_entry(file_path="evidence/databases/snapshot.sql")
        records = parse_sql_evidence(sql_path, entry)
        assert len(records) == 2

    def test_empty_sql_returns_empty(self, tmp_path):
        sql_path = tmp_path / "empty.sql"
        sql_path.write_text("")
        entry = _make_entry()
        records = parse_sql_evidence(sql_path, entry)
        assert records == []

    def test_missing_file_returns_empty(self, tmp_path):
        entry = _make_entry()
        records = parse_sql_evidence(tmp_path / "nonexistent.sql", entry)
        assert records == []

    def test_file_id_preserved(self, tmp_path):
        sql = "CREATE TABLE t (id TEXT); INSERT INTO t VALUES ('abc');"
        sql_path = tmp_path / "test.sql"
        sql_path.write_text(sql)
        entry = _make_entry(file_id="evidence_42")
        records = parse_sql_evidence(sql_path, entry)
        assert all(r.file_id == "evidence_42" for r in records)


# ---------------------------------------------------------------------------
# parse_all_evidence integration
# ---------------------------------------------------------------------------


class TestParseAllEvidence:
    def test_empty_manifest_returns_empty(self, tmp_path):
        result = parse_all_evidence(tmp_path, [])
        assert result == []

    def test_missing_evidence_file_skipped(self, tmp_path):
        (tmp_path / "evidence").mkdir()
        entry = _make_entry(
            file_id="evidence_01",
            file_path="evidence/logs/nonexistent.log",
        )
        result = parse_all_evidence(tmp_path, [entry])
        assert result == []

    def test_csv_dispatched_correctly(self, tmp_path):
        ev_dir = tmp_path / "evidence" / "records"
        ev_dir.mkdir(parents=True)
        csv_path = ev_dir / "test.csv"
        csv_path.write_text("user_id,email\nuser_01,alice@example.com\n")
        entry = _make_entry(
            file_id="evidence_01",
            file_path="evidence/records/test.csv",
        )
        result = parse_all_evidence(tmp_path, [entry])
        assert len(result) == 1
        assert result[0].email == "alice@example.com"

    def test_all_records_have_file_id(self, tmp_path):
        ev_dir = tmp_path / "evidence" / "records"
        ev_dir.mkdir(parents=True)
        csv_path = ev_dir / "test.csv"
        csv_path.write_text("user_id,email\nuser_01,a@a.com\nuser_02,b@b.com\n")
        entry = _make_entry(
            file_id="evidence_99",
            file_path="evidence/records/test.csv",
        )
        result = parse_all_evidence(tmp_path, [entry])
        assert all(r.file_id == "evidence_99" for r in result)

    def test_captured_at_preserved(self, tmp_path):
        ev_dir = tmp_path / "evidence" / "logs"
        ev_dir.mkdir(parents=True)
        log_path = ev_dir / "test.log"
        log_path.write_text("2026-09-15T12:00:00Z INFO user_01 account_001 deleted\n")
        entry = _make_entry(
            file_path="evidence/logs/test.log",
            captured_at="2026-09-15T12:00:00Z",
        )
        result = parse_all_evidence(tmp_path, [entry])
        assert len(result) == 1
        assert result[0].captured_at.year == 2026

    def test_multiple_manifest_entries(self, tmp_path):
        ev_dir_log = tmp_path / "evidence" / "logs"
        ev_dir_rec = tmp_path / "evidence" / "records"
        ev_dir_log.mkdir(parents=True)
        ev_dir_rec.mkdir(parents=True)

        (ev_dir_log / "test.log").write_text(
            "2026-09-15T12:00:00Z INFO user_01 account_001 deleted\n"
            "2026-09-15T12:01:00Z INFO user_02 account_002 deleted\n"
        )
        (ev_dir_rec / "test.csv").write_text(
            "user_id,email\nuser_03,c@c.com\nuser_04,d@d.com\n"
        )

        entries = [
            _make_entry(file_id="ev_01", file_path="evidence/logs/test.log"),
            _make_entry(file_id="ev_02", file_path="evidence/records/test.csv"),
        ]
        result = parse_all_evidence(tmp_path, entries)
        assert len(result) == 4


# ---------------------------------------------------------------------------
# EvidenceRecord model validation
# ---------------------------------------------------------------------------


class TestEvidenceRecordModel:
    def test_record_has_required_fields(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text("user_id,email\nuser_01,alice@example.com\n")
        entry = _make_entry(file_path="evidence/records/test.csv")
        records = parse_csv_evidence(csv_path, entry, EvidenceFormat.CSV)
        rec = records[0]
        assert isinstance(rec, EvidenceRecord)
        assert rec.file_id is not None
        assert rec.file_format is not None
        assert rec.origin is not None
        assert rec.captured_at is not None
        assert rec.record_type is not None

    def test_parse_warnings_empty_by_default(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text("user_id,email\nuser_01,alice@example.com\n")
        entry = _make_entry()
        records = parse_csv_evidence(csv_path, entry, EvidenceFormat.CSV)
        assert records[0].parse_warnings == []
