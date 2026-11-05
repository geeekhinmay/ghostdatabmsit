"""
Identity resolution engine.

Resolves deletion requests to canonical user identities across current profiles
and historical audit logs, establishing the complete identity cluster (historical
emails, phone numbers, email hashes, and full names).

Owned by: Member 3 (Chirag Gowda)
Public function: resolve_identity(request, dataset) -> IdentityResolution
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Union

from code.identity.models import IdentityResolution
from code.models.schemas import DeletionRequest, SystemActivity, UserAuditEntry, UserIdentity

logger = logging.getLogger(__name__)


def _get_field(obj: Any, name: str, default: Any = None) -> Any:
    """Helper to extract a field from a Pydantic model or dictionary."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _normalize_email(email: Optional[str]) -> str:
    """Normalize email address to lowercase stripped format."""
    if not email:
        return ""
    return str(email).strip().lower()


def resolve_identity(
    request: Union[DeletionRequest, Dict[str, Any]],
    dataset: Any,
) -> IdentityResolution:
    """
    Public contract: Resolve current and historical user identities for a deletion request.

    Args:
        request: DeletionRequest object or dict containing case_id, email, requested_at, etc.
        dataset: DatasetBundle object or dict containing user_identities, user_audit_log, etc.

    Returns:
        IdentityResolution with canonical user_id, identity cluster, and audit entries.
    """
    case_id = str(_get_field(request, "case_id", "case_unknown"))
    raw_email = _get_field(request, "email", "")
    normalized_email = _normalize_email(raw_email)

    # Parse audit cutoff if present
    audit_at_val = _get_field(request, "audit_at")
    audit_at: Optional[datetime] = None
    if isinstance(audit_at_val, str):
        try:
            audit_at = datetime.fromisoformat(audit_at_val.replace("Z", "+00:00"))
        except Exception:
            pass
    elif isinstance(audit_at_val, datetime):
        audit_at = audit_at_val

    def _is_le_audit_at(entry: Any) -> bool:
        if not audit_at:
            return True
        t_val = _get_field(entry, "event_time")
        if not t_val:
            return True
        if isinstance(t_val, str):
            try:
                t = datetime.fromisoformat(t_val.replace("Z", "+00:00"))
                return t <= audit_at
            except Exception:
                return True
        elif isinstance(t_val, datetime):
            return t_val <= audit_at
        return True

    # Fast access collections
    identities_by_email = getattr(dataset, "identities_by_email", {}) or {}
    identities_by_user_id = getattr(dataset, "identities_by_user_id", {}) or {}
    user_identities = getattr(dataset, "user_identities", []) or []
    user_audit_log = getattr(dataset, "user_audit_log", []) or []
    system_activity = getattr(dataset, "system_activity", []) or []

    matched_user: Optional[UserIdentity] = None
    matched_by = "UNKNOWN"

    # 1. Direct current email lookup
    if normalized_email:
        if isinstance(identities_by_email, dict) and normalized_email in identities_by_email:
            matched_user = identities_by_email[normalized_email]
            matched_by = "DIRECT_EMAIL"
        else:
            # Fallback iteration over user_identities
            for u in user_identities:
                u_email = _normalize_email(_get_field(u, "email"))
                if u_email == normalized_email:
                    matched_user = u
                    matched_by = "DIRECT_EMAIL"
                    break

    # 2. Historical audit log lookup fallback
    if not matched_user and normalized_email:
        for audit in user_audit_log:
            if not _is_le_audit_at(audit):
                continue
            field_name = _get_field(audit, "field_name", "")
            if field_name == "email":
                old_val = _normalize_email(_get_field(audit, "old_value"))
                new_val = _normalize_email(_get_field(audit, "new_value"))
                if old_val == normalized_email or new_val == normalized_email:
                    uid = _get_field(audit, "user_id")
                    if uid:
                        if isinstance(identities_by_user_id, dict) and uid in identities_by_user_id:
                            matched_user = identities_by_user_id[uid]
                        else:
                            for u in user_identities:
                                if _get_field(u, "user_id") == uid:
                                    matched_user = u
                                    break
                    if matched_user:
                        matched_by = "HISTORICAL_EMAIL"
                        break

    # 3. Handle unidentified subjects
    if not matched_user:
        logger.warning("Subject for case %s (%s) could not be identified", case_id, raw_email)
        return IdentityResolution(
            case_id=case_id,
            user_id=None,
            current_name=None,
            current_email=normalized_email if normalized_email else None,
            current_phone=None,
            current_email_hash=None,
            all_emails=[normalized_email] if normalized_email else [],
            all_phones=[],
            all_email_hashes=[],
            all_names=[],
            emails=[normalized_email] if normalized_email else [],
            phones=[],
            email_hashes=[],
            names=[],
            account_ids=[],
            is_identified=False,
            is_resolved=False,
            matched_by="UNKNOWN",
            audit_entries=[],
            associated_activities=[],
            details={"lookup_status": "UNRESOLVED", "query_email": raw_email},
        )

    # 4. Extract canonical user details
    user_id = str(_get_field(matched_user, "user_id", ""))
    current_name = _get_field(matched_user, "name")
    current_email = _get_field(matched_user, "email")
    current_phone = _get_field(matched_user, "phone")
    current_email_hash = _get_field(matched_user, "email_hash")

    # 5. Build full identity cluster from current snapshot and audit logs
    all_emails_set: Set[str] = set()
    all_phones_set: Set[str] = set()
    all_hashes_set: Set[str] = set()
    all_names_set: Set[str] = set()

    if normalized_email:
        all_emails_set.add(normalized_email)
    if current_email:
        all_emails_set.add(_normalize_email(current_email))
    if current_phone:
        all_phones_set.add(str(current_phone).strip())
    if current_email_hash:
        all_hashes_set.add(str(current_email_hash).strip())
    if current_name:
        all_names_set.add(str(current_name).strip())

    user_audit_entries: List[UserAuditEntry] = []
    account_ids_set: Set[str] = set()
    if user_id:
        num_part = user_id.split('_')[1] if '_' in user_id else user_id
        account_ids_set.add(f"account_{num_part}")
        if num_part.isdigit():
            account_ids_set.add(f"account_{int(num_part):03d}")

    for audit in user_audit_log:
        if _get_field(audit, "user_id") == user_id:
            if not _is_le_audit_at(audit):
                continue
            user_audit_entries.append(audit)
            field_name = _get_field(audit, "field_name", "")
            old_val = _get_field(audit, "old_value", "")
            new_val = _get_field(audit, "new_value", "")

            if field_name == "email":
                if old_val:
                    all_emails_set.add(_normalize_email(old_val))
                if new_val:
                    all_emails_set.add(_normalize_email(new_val))
            elif field_name == "phone":
                if old_val:
                    all_phones_set.add(str(old_val).strip())
                if new_val:
                    all_phones_set.add(str(new_val).strip())
            elif field_name == "email_hash":
                if old_val:
                    all_hashes_set.add(str(old_val).strip())
                if new_val:
                    all_hashes_set.add(str(new_val).strip())
            elif field_name in ["account_id", "account"]:
                if old_val:
                    account_ids_set.add(str(old_val).strip())
                if new_val:
                    account_ids_set.add(str(new_val).strip())

    # Sort audit entries chronologically if event_time is available
    def _audit_sort_key(entry: Any) -> datetime:
        t = _get_field(entry, "event_time")
        if isinstance(t, str):
            try:
                return datetime.fromisoformat(t.replace("Z", "+00:00"))
            except Exception:
                return datetime.min
        elif isinstance(t, datetime):
            return t
        return datetime.min

    user_audit_entries.sort(key=_audit_sort_key)

    # 6. Find correlated system activity events for this user/workflow
    req_at_val = _get_field(request, "requested_at")
    rep_at_val = _get_field(request, "reported_at")
    req_at = None
    rep_at = None
    if isinstance(req_at_val, str):
        try:
            req_at = datetime.fromisoformat(req_at_val.replace("Z", "+00:00"))
        except Exception:
            pass
    elif isinstance(req_at_val, datetime):
        req_at = req_at_val

    if isinstance(rep_at_val, str):
        try:
            rep_at = datetime.fromisoformat(rep_at_val.replace("Z", "+00:00"))
        except Exception:
            pass
    elif isinstance(rep_at_val, datetime):
        rep_at = rep_at_val

    associated_activities: List[SystemActivity] = []
    for act in system_activity:
        if not _is_le_audit_at(act):
            continue
        act_details = str(_get_field(act, "details", ""))
        act_res = str(_get_field(act, "resource_id", ""))
        # Check direct user reference in details
        if user_id in act_details or any(e in act_details for e in all_emails_set):
            associated_activities.append(act)
            if act_res.startswith("account_"):
                account_ids_set.add(act_res)
        elif req_at and rep_at:
            act_t_val = _get_field(act, "event_time")
            act_t = None
            if isinstance(act_t_val, str):
                try:
                    act_t = datetime.fromisoformat(act_t_val.replace("Z", "+00:00"))
                except Exception:
                    pass
            elif isinstance(act_t_val, datetime):
                act_t = act_t_val

            if act_t and req_at <= act_t <= rep_at:
                src = _get_field(act, "source_system", "")
                if src == "deletion_worker":
                    # Check if resource matches user's convention
                    if act_res == f"account_{user_id.split('_')[1]}" or act_res == f"account_{int(user_id.split('_')[1]):03d}":
                        associated_activities.append(act)
                        account_ids_set.add(act_res)

    return IdentityResolution(
        case_id=case_id,
        user_id=user_id,
        current_name=str(current_name) if current_name else None,
        current_email=str(current_email) if current_email else None,
        current_phone=str(current_phone) if current_phone else None,
        current_email_hash=str(current_email_hash) if current_email_hash else None,
        all_emails=sorted(all_emails_set),
        all_phones=sorted(all_phones_set),
        all_email_hashes=sorted(all_hashes_set),
        all_names=sorted(all_names_set),
        emails=sorted(all_emails_set),
        phones=sorted(all_phones_set),
        email_hashes=sorted(all_hashes_set),
        names=sorted(all_names_set),
        account_ids=sorted(account_ids_set),
        is_identified=True,
        is_resolved=True,
        matched_by=matched_by,
        audit_entries=user_audit_entries,
        associated_activities=associated_activities,
        details={
            "lookup_status": "IDENTIFIED",
            "historical_email_count": len(all_emails_set),
            "historical_phone_count": len(all_phones_set),
            "historical_hash_count": len(all_hashes_set),
        },
    )

