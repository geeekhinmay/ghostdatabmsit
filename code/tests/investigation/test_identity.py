"""
Unit tests for code/identity/resolver.py

Covers:
- Direct email matching (DIRECT_EMAIL)
- Historical email matching via user_audit_log (HISTORICAL_EMAIL)
- Phone and email_hash cluster population
- Multiple historical emails/phones
- Unknown/unregistered user handling
- Identity cluster completeness
- case_id propagation
- Full IdentityResolution model validation

Owned by: Member 3 (Chirag Gowda)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from code.identity import IdentityResolution, resolve_identity
from code.models.schemas import DatasetBundle, DeletionRequest, UserAuditEntry, UserIdentity
from code.models.enums import ReportedStatus


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _make_user(
    user_id: str,
    email: str,
    name: str = "Test User",
    phone: str = "+1-555-0000",
    email_hash: str = "aabbcc",
    updated_at: str = "2026-01-01T00:00:00Z",
) -> UserIdentity:
    return UserIdentity(
        user_id=user_id,
        name=name,
        email=email,
        phone=phone,
        email_hash=email_hash,
        updated_at=_dt(updated_at),
    )


def _make_audit(
    audit_id: str,
    user_id: str,
    field_name: str,
    old_value: str,
    new_value: str,
    event_time: str = "2025-06-01T00:00:00Z",
) -> UserAuditEntry:
    return UserAuditEntry(
        audit_id=audit_id,
        user_id=user_id,
        event_time=_dt(event_time),
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
    )


def _make_request(
    case_id: str = "case_001",
    email: str = "test@example.com",
    requested_at: str = "2026-09-01T10:00:00Z",
    reported_at: str = "2026-09-05T10:00:00Z",
    audit_at: str = "2026-09-06T00:00:00Z",
    request_text: str = "Please delete my account.",
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


def _make_dataset(
    identities: list[UserIdentity] | None = None,
    audit_log: list[UserAuditEntry] | None = None,
    system_activity: list | None = None,
) -> DatasetBundle:
    """Build a minimal DatasetBundle mock for identity tests."""
    identities = identities or []
    audit_log = audit_log or []
    system_activity = system_activity or []

    email_index = {u.email.strip().lower(): u for u in identities}
    uid_index = {u.user_id: u for u in identities}

    return DatasetBundle(
        deletion_requests=[],
        sample_requests=[],
        user_identities=identities,
        user_audit_log=audit_log,
        system_activity=system_activity,
        deletion_rules=[],
        evidence_manifest=[],
        identities_by_email=email_index,
        identities_by_user_id=uid_index,
        rules_by_category={},
        manifest_by_file_id={},
        activity_by_id={},
        audit_by_id={},
    )


# ---------------------------------------------------------------------------
# 1. Direct email matching
# ---------------------------------------------------------------------------

class TestDirectEmailMatch:

    def test_exact_email_returns_identified(self):
        user = _make_user("user_01", "amina.elmasri@gmail.com", name="Amina Elmasri")
        dataset = _make_dataset(identities=[user])
        req = _make_request(case_id="case_001", email="amina.elmasri@gmail.com")

        result = resolve_identity(req, dataset)

        assert isinstance(result, IdentityResolution)
        assert result.is_identified is True
        assert result.user_id == "user_01"
        assert result.matched_by == "DIRECT_EMAIL"

    def test_case_insensitive_email_match(self):
        user = _make_user("user_02", "alice@example.com")
        dataset = _make_dataset(identities=[user])
        req = _make_request(email="ALICE@EXAMPLE.COM")

        result = resolve_identity(req, dataset)

        assert result.is_identified is True
        assert result.user_id == "user_02"
        assert result.matched_by == "DIRECT_EMAIL"

    def test_email_whitespace_trimmed(self):
        user = _make_user("user_03", "bob@example.com")
        dataset = _make_dataset(identities=[user])
        req = _make_request(email="  bob@example.com  ")

        result = resolve_identity(req, dataset)

        assert result.is_identified is True
        assert result.user_id == "user_03"

    def test_case_id_propagated(self):
        user = _make_user("user_04", "carol@example.com")
        dataset = _make_dataset(identities=[user])
        req = _make_request(case_id="case_XYZ", email="carol@example.com")

        result = resolve_identity(req, dataset)

        assert result.case_id == "case_XYZ"

    def test_current_identity_fields_populated(self):
        user = _make_user(
            "user_05", "dave@example.com",
            name="Dave Smith", phone="+1-555-1234",
            email_hash="hash_dave"
        )
        dataset = _make_dataset(identities=[user])
        req = _make_request(email="dave@example.com")

        result = resolve_identity(req, dataset)

        assert result.current_name == "Dave Smith"
        assert result.current_email == "dave@example.com"
        assert result.current_phone == "+1-555-1234"
        assert result.current_email_hash == "hash_dave"

    def test_all_emails_contains_match_and_current(self):
        user = _make_user("user_06", "eve@example.com")
        dataset = _make_dataset(identities=[user])
        req = _make_request(email="eve@example.com")

        result = resolve_identity(req, dataset)

        assert "eve@example.com" in result.all_emails

    def test_multiple_users_correct_one_matched(self):
        users = [
            _make_user("user_07", "user7@example.com"),
            _make_user("user_08", "user8@example.com"),
            _make_user("user_09", "user9@example.com"),
        ]
        dataset = _make_dataset(identities=users)
        req = _make_request(email="user8@example.com")

        result = resolve_identity(req, dataset)

        assert result.user_id == "user_08"


# ---------------------------------------------------------------------------
# 2. Historical email matching
# ---------------------------------------------------------------------------

class TestHistoricalEmailMatch:

    def test_old_email_in_audit_log_resolves_to_user(self):
        """User changed email; request uses old email => HISTORICAL_EMAIL match."""
        user = _make_user("user_12", "minjun.kim@newdomain.com", name="Minjun Kim")
        audit = _make_audit(
            "audit_001", "user_12", "email",
            old_value="minjun.kim90@gmail.com",
            new_value="minjun.kim@newdomain.com",
            event_time="2026-03-01T00:00:00Z",
        )
        dataset = _make_dataset(identities=[user], audit_log=[audit])
        req = _make_request(email="minjun.kim90@gmail.com")

        result = resolve_identity(req, dataset)

        assert result.is_identified is True
        assert result.user_id == "user_12"
        assert result.matched_by == "HISTORICAL_EMAIL"

    def test_new_email_as_old_value_in_audit_log(self):
        """Audit new_value matches request email (unusual but valid)."""
        user = _make_user("user_13", "current@example.com")
        audit = _make_audit(
            "audit_002", "user_13", "email",
            old_value="old@example.com",
            new_value="current@example.com",
        )
        dataset = _make_dataset(identities=[user], audit_log=[audit])
        req = _make_request(email="current@example.com")

        result = resolve_identity(req, dataset)

        # current@example.com is now the current email, so DIRECT_EMAIL wins
        assert result.is_identified is True
        assert result.user_id == "user_13"

    def test_historical_email_included_in_all_emails(self):
        """Cluster must include the historical email."""
        user = _make_user("user_14", "new@example.com")
        audit = _make_audit("audit_003", "user_14", "email",
                            old_value="old@example.com", new_value="new@example.com")
        dataset = _make_dataset(identities=[user], audit_log=[audit])
        req = _make_request(email="old@example.com")

        result = resolve_identity(req, dataset)

        assert "old@example.com" in result.all_emails
        assert "new@example.com" in result.all_emails

    def test_non_email_audit_entries_ignored_for_fallback(self):
        """Phone-change audit entries must NOT be used to match email."""
        user = _make_user("user_15", "user15@example.com")
        audit = _make_audit("audit_004", "user_15", "phone",
                            old_value="+1-000-0001", new_value="+1-000-0002")
        dataset = _make_dataset(identities=[user], audit_log=[audit])
        req = _make_request(email="unknown@nowhere.com")

        result = resolve_identity(req, dataset)

        assert result.is_identified is False
        assert result.matched_by == "UNKNOWN"

    def test_audit_entries_sorted_chronologically(self):
        """audit_entries returned must be in event_time order."""
        user = _make_user("user_16", "latest@example.com")
        audit_later = _make_audit("audit_006", "user_16", "email",
                                  old_value="middle@example.com", new_value="latest@example.com",
                                  event_time="2026-06-01T00:00:00Z")
        audit_earlier = _make_audit("audit_005", "user_16", "email",
                                    old_value="first@example.com", new_value="middle@example.com",
                                    event_time="2026-01-01T00:00:00Z")
        dataset = _make_dataset(identities=[user], audit_log=[audit_later, audit_earlier])
        req = _make_request(email="latest@example.com")

        result = resolve_identity(req, dataset)

        assert len(result.audit_entries) == 2
        assert result.audit_entries[0].audit_id == "audit_005"
        assert result.audit_entries[1].audit_id == "audit_006"


# ---------------------------------------------------------------------------
# 3. Identity cluster population
# ---------------------------------------------------------------------------

class TestIdentityCluster:

    def test_all_emails_includes_audit_history(self):
        user = _make_user("user_20", "current@example.com")
        audits = [
            _make_audit("a1", "user_20", "email", "first@example.com", "second@example.com"),
            _make_audit("a2", "user_20", "email", "second@example.com", "current@example.com"),
        ]
        dataset = _make_dataset(identities=[user], audit_log=audits)
        req = _make_request(email="current@example.com")

        result = resolve_identity(req, dataset)

        assert "first@example.com" in result.all_emails
        assert "second@example.com" in result.all_emails
        assert "current@example.com" in result.all_emails

    def test_all_phones_includes_audit_history(self):
        user = _make_user("user_21", "user21@example.com", phone="+1-555-9999")
        audit = _make_audit("a3", "user_21", "phone", "+1-555-0001", "+1-555-9999")
        dataset = _make_dataset(identities=[user], audit_log=[audit])
        req = _make_request(email="user21@example.com")

        result = resolve_identity(req, dataset)

        assert "+1-555-0001" in result.all_phones
        assert "+1-555-9999" in result.all_phones

    def test_all_email_hashes_includes_audit_history(self):
        user = _make_user("user_22", "user22@example.com", email_hash="newhash")
        audit = _make_audit("a4", "user_22", "email_hash", "oldhash", "newhash")
        dataset = _make_dataset(identities=[user], audit_log=[audit])
        req = _make_request(email="user22@example.com")

        result = resolve_identity(req, dataset)

        assert "oldhash" in result.all_email_hashes
        assert "newhash" in result.all_email_hashes

    def test_cluster_no_duplicates(self):
        """If request email equals current email, it should appear only once."""
        user = _make_user("user_23", "nodupe@example.com")
        dataset = _make_dataset(identities=[user])
        req = _make_request(email="nodupe@example.com")

        result = resolve_identity(req, dataset)

        assert result.all_emails.count("nodupe@example.com") == 1

    def test_other_users_audit_entries_excluded(self):
        """Audit entries for different users must not pollute identity cluster."""
        user = _make_user("user_24", "user24@example.com")
        other_audit = _make_audit("a5", "user_99", "email",
                                  "other_old@example.com", "other_new@example.com")
        dataset = _make_dataset(identities=[user], audit_log=[other_audit])
        req = _make_request(email="user24@example.com")

        result = resolve_identity(req, dataset)

        assert "other_old@example.com" not in result.all_emails
        assert "other_new@example.com" not in result.all_emails
        assert result.audit_entries == []


# ---------------------------------------------------------------------------
# 4. Unidentified / unknown user
# ---------------------------------------------------------------------------

class TestUnknownUser:

    def test_unregistered_email_returns_not_identified(self):
        dataset = _make_dataset(identities=[])
        req = _make_request(email="ghost@nowhere.com")

        result = resolve_identity(req, dataset)

        assert isinstance(result, IdentityResolution)
        assert result.is_identified is False
        assert result.matched_by == "UNKNOWN"
        assert result.user_id is None

    def test_unknown_result_includes_query_email_in_all_emails(self):
        dataset = _make_dataset(identities=[])
        req = _make_request(email="ghost@nowhere.com")

        result = resolve_identity(req, dataset)

        assert "ghost@nowhere.com" in result.all_emails

    def test_unknown_result_case_id_propagated(self):
        dataset = _make_dataset(identities=[])
        req = _make_request(case_id="case_999", email="ghost@nowhere.com")

        result = resolve_identity(req, dataset)

        assert result.case_id == "case_999"

    def test_unknown_result_audit_entries_empty(self):
        dataset = _make_dataset(identities=[])
        req = _make_request(email="ghost@nowhere.com")

        result = resolve_identity(req, dataset)

        assert result.audit_entries == []

    def test_unknown_result_all_phones_empty(self):
        dataset = _make_dataset(identities=[])
        req = _make_request(email="ghost@nowhere.com")

        result = resolve_identity(req, dataset)

        assert result.all_phones == []

    def test_empty_email_returns_not_identified(self):
        dataset = _make_dataset(identities=[_make_user("user_30", "someone@example.com")])
        req = _make_request(email="")

        result = resolve_identity(req, dataset)

        assert result.is_identified is False
        assert result.matched_by == "UNKNOWN"


# ---------------------------------------------------------------------------
# 5. Return type and model contract
# ---------------------------------------------------------------------------

class TestReturnContract:

    def test_returns_identity_resolution_instance(self):
        dataset = _make_dataset(identities=[_make_user("user_40", "test@example.com")])
        req = _make_request(email="test@example.com")

        result = resolve_identity(req, dataset)

        assert isinstance(result, IdentityResolution)

    def test_identified_result_has_all_required_fields(self):
        user = _make_user("user_41", "full@example.com", name="Full Name",
                          phone="+1-555-0001", email_hash="fullhash")
        dataset = _make_dataset(identities=[user])
        req = _make_request(email="full@example.com")

        result = resolve_identity(req, dataset)

        assert result.case_id is not None
        assert result.user_id is not None
        assert result.current_name is not None
        assert result.current_email is not None
        assert result.current_phone is not None
        assert result.current_email_hash is not None
        assert isinstance(result.all_emails, list)
        assert isinstance(result.all_phones, list)
        assert isinstance(result.all_email_hashes, list)
        assert isinstance(result.all_names, list)
        assert isinstance(result.is_identified, bool)
        assert isinstance(result.matched_by, str)
        assert isinstance(result.audit_entries, list)
        assert isinstance(result.associated_activities, list)
        assert isinstance(result.details, dict)

    def test_unidentified_result_has_all_required_fields(self):
        dataset = _make_dataset(identities=[])
        req = _make_request(email="nobody@example.com")

        result = resolve_identity(req, dataset)

        assert result.case_id is not None
        assert result.user_id is None
        assert isinstance(result.all_emails, list)
        assert isinstance(result.all_phones, list)
        assert isinstance(result.all_email_hashes, list)
        assert isinstance(result.is_identified, bool)
        assert result.is_identified is False

    def test_accepts_dict_dataset(self):
        """resolve_identity must work when dataset-like object uses dict interface (fallback)."""
        user = _make_user("user_42", "dict_user@example.com")
        dataset_dict = MagicMock()
        dataset_dict.identities_by_email = {"dict_user@example.com": user}
        dataset_dict.identities_by_user_id = {"user_42": user}
        dataset_dict.user_identities = [user]
        dataset_dict.user_audit_log = []
        dataset_dict.system_activity = []

        req = _make_request(email="dict_user@example.com")
        result = resolve_identity(req, dataset_dict)

        assert result.is_identified is True
        assert result.user_id == "user_42"

    def test_all_emails_sorted(self):
        """all_emails list must be sorted alphabetically."""
        user = _make_user("user_43", "z@example.com")
        audits = [
            _make_audit("ax1", "user_43", "email", "a@example.com", "z@example.com"),
        ]
        dataset = _make_dataset(identities=[user], audit_log=audits)
        req = _make_request(email="z@example.com")

        result = resolve_identity(req, dataset)

        assert result.all_emails == sorted(result.all_emails)

    def test_details_dict_has_lookup_status(self):
        user = _make_user("user_44", "detail@example.com")
        dataset = _make_dataset(identities=[user])
        req = _make_request(email="detail@example.com")

        result = resolve_identity(req, dataset)

        assert "lookup_status" in result.details
        assert result.details["lookup_status"] == "IDENTIFIED"

    def test_unidentified_details_dict_has_lookup_status(self):
        dataset = _make_dataset(identities=[])
        req = _make_request(email="unknown@example.com")

        result = resolve_identity(req, dataset)

        assert "lookup_status" in result.details
        assert result.details["lookup_status"] == "UNRESOLVED"


# ---------------------------------------------------------------------------
# 6. Audit Cutoff and Account ID Handling (Point 1 & Point 2 Verification)
# ---------------------------------------------------------------------------

class TestIdentityAuditCutoffAndAccounts:
    """Verifies that identity relationships respect audit_at cutoff and account IDs."""

    def test_audit_entries_after_audit_at_are_excluded(self):
        """Audit entries with event_time > audit_at must be excluded from the cluster."""
        user = _make_user("user_50", "current@example.com", phone="+1-555-0001")
        audit_past = _make_audit(
            "aud_p", "user_50", "phone", "+1-555-0000", "+1-555-0001",
            event_time="2026-08-01T00:00:00Z"
        )
        audit_future = _make_audit(
            "aud_f", "user_50", "phone", "+1-555-0001", "+1-555-9999",
            event_time="2026-10-01T00:00:00Z"
        )
        dataset = _make_dataset(identities=[user], audit_log=[audit_past, audit_future])
        req = _make_request(
            email="current@example.com",
            audit_at="2026-09-01T00:00:00Z"
        )

        result = resolve_identity(req, dataset)

        assert result.is_identified is True
        assert "+1-555-9999" not in result.all_phones
        assert "+1-555-0000" in result.all_phones
        assert len(result.audit_entries) == 1
        assert result.audit_entries[0].audit_id == "aud_p"

    def test_historical_email_fallback_respects_audit_at(self):
        """Fallback lookup must ignore email changes that occurred after audit_at."""
        user = _make_user("user_51", "new@example.com")
        audit_future = _make_audit(
            "aud_fut", "user_51", "email", "future_old@example.com", "new@example.com",
            event_time="2026-10-01T00:00:00Z"
        )
        dataset = _make_dataset(identities=[user], audit_log=[audit_future])
        req = _make_request(
            email="future_old@example.com",
            audit_at="2026-09-01T00:00:00Z"
        )

        result = resolve_identity(req, dataset)

        # At audit_at (2026-09-01), the email change hadn't happened yet
        assert result.is_identified is False
        assert result.matched_by == "UNKNOWN"

    def test_account_ids_populated_from_convention_and_activities(self):
        """Account IDs must be populated from user ID and linked system activities."""
        from code.models.schemas import SystemActivity
        user = _make_user("user_52", "account_test@example.com")
        act = SystemActivity(
            activity_id="act_01",
            event_time=_dt("2026-08-15T00:00:00Z"),
            event_type="LINK_RESOURCE_IDENTITY",
            source_system="data_catalog",
            target_system="account_service",
            resource_id="account_9988",
            reported_result="SUCCESS",
            details="Linked account_9988 to user_52 and account_test@example.com",
        )
        dataset = _make_dataset(identities=[user], system_activity=[act])
        req = _make_request(
            email="account_test@example.com",
            audit_at="2026-09-01T00:00:00Z"
        )

        result = resolve_identity(req, dataset)

        assert result.is_identified is True
        assert "account_52" in result.account_ids
        assert "account_9988" in result.account_ids


