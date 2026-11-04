"""
Policy rules engine based on official deletion_rules.csv.

Maps resource types, systems, and contextual conditions to required treatments:
DELETE, REDACT, ANONYMIZE, or RETAIN.

Owned by: Member 4 (Hrushikesh)
Module: code/policy/rules.py
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Union
from code.models.enums import RequiredAction
from code.models.schemas import DeletionRule


# Canonical rules from official dataset/deletion_rules.csv
DEFAULT_RULES: Dict[str, Dict[str, Any]] = {
    "rule_01": {
        "rule_id": "rule_01",
        "data_category": "USER_PROFILE",
        "condition": "Always",
        "required_action": RequiredAction.DELETE,
    },
    "rule_02": {
        "rule_id": "rule_02",
        "data_category": "SECONDARY_IDENTIFIER",
        "condition": "Always",
        "required_action": RequiredAction.DELETE,
    },
    "rule_03": {
        "rule_id": "rule_03",
        "data_category": "SEARCH_INDEX_ENTRY",
        "condition": "Always",
        "required_action": RequiredAction.DELETE,
    },
    "rule_04": {
        "rule_id": "rule_04",
        "data_category": "CACHE_ENTRY",
        "condition": "Always",
        "required_action": RequiredAction.DELETE,
    },
    "rule_05": {
        "rule_id": "rule_05",
        "data_category": "SUPPORT_MESSAGE",
        "condition": "Conversation contains shared customer, agent, or order context that must be retained",
        "required_action": RequiredAction.REDACT,
    },
    "rule_06": {
        "rule_id": "rule_06",
        "data_category": "SUPPORT_ATTACHMENT",
        "condition": "Attachment belongs only to the deletion subject",
        "required_action": RequiredAction.DELETE,
    },
    "rule_07": {
        "rule_id": "rule_07",
        "data_category": "ANALYTICS_PROFILE",
        "condition": "Record is still attributable to a user",
        "required_action": RequiredAction.ANONYMIZE,
    },
    "rule_08": {
        "rule_id": "rule_08",
        "data_category": "PRODUCT_TELEMETRY",
        "condition": "Record is still attributable to a user",
        "required_action": RequiredAction.ANONYMIZE,
    },
    "rule_09": {
        "rule_id": "rule_09",
        "data_category": "USER_EXPORT",
        "condition": "Always",
        "required_action": RequiredAction.DELETE,
    },
    "rule_10": {
        "rule_id": "rule_10",
        "data_category": "MARKETING_PROFILE",
        "condition": "Always",
        "required_action": RequiredAction.DELETE,
    },
    "rule_11": {
        "rule_id": "rule_11",
        "data_category": "EMAIL_DELIVERY_LOG",
        "condition": "Log contains a user email address",
        "required_action": RequiredAction.REDACT,
    },
    "rule_12": {
        "rule_id": "rule_12",
        "data_category": "SECURITY_AUDIT_LOG",
        "condition": "Record is within the supplied retention period",
        "required_action": RequiredAction.RETAIN,
    },
    "rule_13": {
        "rule_id": "rule_13",
        "data_category": "LEGAL_HOLD_RECORD",
        "condition": "A supplied legal hold is active",
        "required_action": RequiredAction.RETAIN,
    },
    "rule_14": {
        "rule_id": "rule_14",
        "data_category": "BACKUP_ARCHIVE",
        "condition": "Restore access can be blocked",
        "required_action": RequiredAction.RETAIN,
    },
    "rule_15": {
        "rule_id": "rule_15",
        "data_category": "ACCOUNT_TOMBSTONE",
        "condition": "Account is deleted and only a stable internal user_id is needed to preserve references to retained records",
        "required_action": RequiredAction.REDACT,
    },
}


def infer_data_category(record: Any) -> str:
    """
    Infer the data_category from a record object or dictionary.
    Examines explicit category, record_type, system_id, and resource_id.
    """
    if isinstance(record, dict):
        cat = record.get("data_category") or record.get("record_type") or ""
        sys_id = record.get("system_id") or ""
        res_id = record.get("resource_id") or ""
    else:
        cat = getattr(record, "data_category", None) or getattr(record, "record_type", None) or ""
        sys_id = getattr(record, "system_id", None) or ""
        res_id = getattr(record, "resource_id", None) or ""

    cat_upper = cat.upper()
    sys_upper = sys_id.upper()
    res_upper = res_id.upper()

    # Exact standard categories
    if cat_upper in [
        "USER_PROFILE", "SECONDARY_IDENTIFIER", "SEARCH_INDEX_ENTRY", "CACHE_ENTRY",
        "SUPPORT_MESSAGE", "SUPPORT_ATTACHMENT", "ANALYTICS_PROFILE", "PRODUCT_TELEMETRY",
        "USER_EXPORT", "MARKETING_PROFILE", "EMAIL_DELIVERY_LOG", "SECURITY_AUDIT_LOG",
        "LEGAL_HOLD_RECORD", "BACKUP_ARCHIVE", "ACCOUNT_TOMBSTONE"
    ]:
        return cat_upper

    # Tombstones
    if "TOMBSTONE" in cat_upper or "TOMBSTONE" in res_upper or "TOMBSTONE" in sys_upper:
        return "ACCOUNT_TOMBSTONE"

    # Search indices
    if "SEARCH" in cat_upper or "SEARCH" in sys_upper or "SEARCH" in res_upper:
        return "SEARCH_INDEX_ENTRY"

    # Exports
    if "EXPORT" in cat_upper or "EXPORT" in sys_upper or "EXPORT" in res_upper:
        return "USER_EXPORT"

    # Support attachments vs messages
    if "ATTACHMENT" in cat_upper or "ATTACHMENT" in res_upper:
        return "SUPPORT_ATTACHMENT"
    if "SUPPORT" in cat_upper or "SUPPORT" in sys_upper or "SUPPORT" in res_upper:
        # If resource_id or record indicates an attachment (doc, image, id document)
        if any(ext in res_upper for ext in ["DOC", "PDF", "ATTACH", "IMAGE", "PASSPORT", "ID"]):
            return "SUPPORT_ATTACHMENT"
        return "SUPPORT_MESSAGE"

    # Analytics / Telemetry
    if "ANALYTIC" in cat_upper or "ANALYTIC" in sys_upper or "ANALYTIC" in res_upper:
        return "ANALYTICS_PROFILE"
    if "TELEMETRY" in cat_upper or "TELEMETRY" in sys_upper:
        return "PRODUCT_TELEMETRY"

    # Marketing
    if "MARKETING" in cat_upper or "MARKETING" in sys_upper:
        return "MARKETING_PROFILE"

    # Email delivery logs
    if "EMAIL" in sys_upper and "LOG" in cat_upper:
        return "EMAIL_DELIVERY_LOG"

    # Security audit / Audit logs
    if "AUDIT" in cat_upper or "SECURITY" in sys_upper or "AUDIT" in res_upper:
        return "SECURITY_AUDIT_LOG"

    # Legal hold
    if "LEGAL" in cat_upper or "HOLD" in cat_upper or "LEGAL" in sys_upper:
        return "LEGAL_HOLD_RECORD"

    # Backups
    if "BACKUP" in cat_upper or "BACKUP" in sys_upper or "BACKUP" in res_upper:
        return "BACKUP_ARCHIVE"

    # Cache
    if "CACHE" in cat_upper or "CACHE" in sys_upper:
        return "CACHE_ENTRY"

    # Account service / User profile
    if "ACCOUNT" in sys_upper or "ACCOUNT" in res_upper or "USER" in cat_upper:
        return "USER_PROFILE"

    return "USER_PROFILE"


def get_required_action_for_category(category: str) -> RequiredAction:
    """Return the required policy action for a given data category."""
    cat_upper = category.upper()
    category_map = {
        "USER_PROFILE": RequiredAction.DELETE,
        "SECONDARY_IDENTIFIER": RequiredAction.DELETE,
        "SEARCH_INDEX_ENTRY": RequiredAction.DELETE,
        "CACHE_ENTRY": RequiredAction.DELETE,
        "SUPPORT_ATTACHMENT": RequiredAction.DELETE,
        "USER_EXPORT": RequiredAction.DELETE,
        "MARKETING_PROFILE": RequiredAction.DELETE,
        "SUPPORT_MESSAGE": RequiredAction.REDACT,
        "EMAIL_DELIVERY_LOG": RequiredAction.REDACT,
        "ACCOUNT_TOMBSTONE": RequiredAction.REDACT,
        "ANALYTICS_PROFILE": RequiredAction.ANONYMIZE,
        "PRODUCT_TELEMETRY": RequiredAction.ANONYMIZE,
        "SECURITY_AUDIT_LOG": RequiredAction.RETAIN,
        "LEGAL_HOLD_RECORD": RequiredAction.RETAIN,
        "BACKUP_ARCHIVE": RequiredAction.RETAIN,
    }
    return category_map.get(cat_upper, RequiredAction.DELETE)


def resolve_rule_for_record(
    record: Any,
    rules: Optional[Union[list, dict]] = None,
) -> DeletionRule:
    """
    Resolves the DeletionRule matching a record.
    Uses custom rules bundle if provided, otherwise default canonical rules.
    """
    category = infer_data_category(record)

    # Check provided rules if available
    if rules:
        if isinstance(rules, dict):
            for r in rules.values():
                cat = getattr(r, "data_category", None) or (r.get("data_category") if isinstance(r, dict) else None)
                if cat and cat.upper() == category:
                    if isinstance(r, DeletionRule):
                        return r
                    action = r.get("required_action")
                    if isinstance(action, str):
                        action = RequiredAction(action)
                    return DeletionRule(
                        rule_id=r.get("rule_id", "rule_custom"),
                        data_category=cat,
                        condition=r.get("condition", ""),
                        required_action=action,
                    )
        elif isinstance(rules, list):
            for r in rules:
                cat = getattr(r, "data_category", None) or (r.get("data_category") if isinstance(r, dict) else None)
                if cat and cat.upper() == category:
                    if isinstance(r, DeletionRule):
                        return r
                    action = r.get("required_action")
                    if isinstance(action, str):
                        action = RequiredAction(action)
                    return DeletionRule(
                        rule_id=r.get("rule_id", "rule_custom"),
                        data_category=cat,
                        condition=r.get("condition", ""),
                        required_action=action,
                    )

    # Fallback to canonical default rules
    for item in DEFAULT_RULES.values():
        if item["data_category"] == category:
            return DeletionRule(
                rule_id=item["rule_id"],
                data_category=item["data_category"],
                condition=item["condition"],
                required_action=item["required_action"],
            )

    # Default fallback
    return DeletionRule(
        rule_id="rule_fallback",
        data_category=category,
        condition="Always",
        required_action=get_required_action_for_category(category),
    )
