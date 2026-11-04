"""
Unit tests for policy rules mapping and condition evaluation (code/policy/rules.py).
"""

import pytest
from code.models.enums import RequiredAction
from code.policy.rules import (
    DEFAULT_RULES,
    get_required_action_for_category,
    infer_data_category,
    resolve_rule_for_record,
)


def test_default_rules_coverage():
    """Verify that all 15 rules from deletion_rules.csv are defined."""
    assert len(DEFAULT_RULES) == 15
    for i in range(1, 16):
        rule_key = f"rule_{i:02d}"
        assert rule_key in DEFAULT_RULES
        assert "data_category" in DEFAULT_RULES[rule_key]
        assert "condition" in DEFAULT_RULES[rule_key]
        assert "required_action" in DEFAULT_RULES[rule_key]


def test_required_actions_mapping():
    """Verify standard actions for primary categories."""
    assert get_required_action_for_category("USER_PROFILE") == RequiredAction.DELETE
    assert get_required_action_for_category("SEARCH_INDEX_ENTRY") == RequiredAction.DELETE
    assert get_required_action_for_category("CACHE_ENTRY") == RequiredAction.DELETE
    assert get_required_action_for_category("USER_EXPORT") == RequiredAction.DELETE
    assert get_required_action_for_category("MARKETING_PROFILE") == RequiredAction.DELETE
    assert get_required_action_for_category("SUPPORT_ATTACHMENT") == RequiredAction.DELETE
    assert get_required_action_for_category("SUPPORT_MESSAGE") == RequiredAction.REDACT
    assert get_required_action_for_category("EMAIL_DELIVERY_LOG") == RequiredAction.REDACT
    assert get_required_action_for_category("ACCOUNT_TOMBSTONE") == RequiredAction.REDACT
    assert get_required_action_for_category("ANALYTICS_PROFILE") == RequiredAction.ANONYMIZE
    assert get_required_action_for_category("PRODUCT_TELEMETRY") == RequiredAction.ANONYMIZE
    assert get_required_action_for_category("SECURITY_AUDIT_LOG") == RequiredAction.RETAIN
    assert get_required_action_for_category("LEGAL_HOLD_RECORD") == RequiredAction.RETAIN
    assert get_required_action_for_category("BACKUP_ARCHIVE") == RequiredAction.RETAIN


def test_infer_data_category_from_attributes():
    """Verify category inference from diverse record attributes."""
    # Tombstone
    tombstone_rec = {"system_id": "identity_service", "resource_id": "tombstone_9178"}
    assert infer_data_category(tombstone_rec) == "ACCOUNT_TOMBSTONE"

    # Search
    search_rec = {"system_id": "search_service", "resource_id": "search_052"}
    assert infer_data_category(search_rec) == "SEARCH_INDEX_ENTRY"

    # Export
    export_rec = {"system_id": "export_service", "resource_id": "export_001"}
    assert infer_data_category(export_rec) == "USER_EXPORT"

    # Support attachment
    attach_rec = {"system_id": "support_platform", "resource_id": "support_doc_001"}
    assert infer_data_category(attach_rec) == "SUPPORT_ATTACHMENT"

    # Support message
    msg_rec = {"system_id": "support_platform", "resource_id": "support_864"}
    assert infer_data_category(msg_rec) == "SUPPORT_MESSAGE"

    # Analytics
    analytics_rec = {"system_id": "analytics_platform", "resource_id": "analytics_2034"}
    assert infer_data_category(analytics_rec) == "ANALYTICS_PROFILE"

    # Security audit log
    audit_rec = {"system_id": "security_service", "resource_id": "audit_record_2016"}
    assert infer_data_category(audit_rec) == "SECURITY_AUDIT_LOG"

    # Backup
    backup_rec = {"system_id": "backup_service", "resource_id": "backup_4978"}
    assert infer_data_category(backup_rec) == "BACKUP_ARCHIVE"


def test_resolve_rule_for_record():
    """Verify resolve_rule_for_record returns matching DeletionRule."""
    rec = {"system_id": "security_service", "resource_id": "audit_record_101"}
    rule = resolve_rule_for_record(rec)
    assert rule.required_action == RequiredAction.RETAIN
    assert rule.data_category == "SECURITY_AUDIT_LOG"

    rec2 = {"system_id": "search_service", "resource_id": "search_101"}
    rule2 = resolve_rule_for_record(rec2)
    assert rule2.required_action == RequiredAction.DELETE
    assert rule2.data_category == "SEARCH_INDEX_ENTRY"
