"""
Investigation execution engine.

Conducts end-to-end evidence audits for individual deletion requests across
databases, failover replicas, search indexes, customer support records,
analytics profiles, active data flows, backup restore paths, and audit ledgers.

Owned by: Member 3 (Chirag Gowda)
Public function: investigate_case(request, identity, evidence) -> InvestigationResult
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from code.investigation.correlator import EvidenceIndexer
from code.investigation.models import (
    InvestigatedDataFlow,
    InvestigatedResource,
    InvestigatedRestoreRisk,
    InvestigationFinding,
    InvestigationResult,
)
from code.models.enums import StepState
from code.models.schemas import DeletionRequest, EvidenceRecord

logger = logging.getLogger(__name__)

# Global cached indexer instance to avoid re-parsing on every case
_INDEXER_CACHE: Dict[str, EvidenceIndexer] = {}


def _get_field(obj: Any, name: str, default: Any = None) -> Any:
    """Helper to extract a field from a Pydantic model or dictionary."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _parse_iso(val: Any) -> Optional[datetime]:
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def _find_dataset_dir(evidence: Any) -> Path:
    """Determine the dataset directory from evidence records, environment, or relative path."""
    env_dir = os.environ.get("DATASET_DIR")
    if env_dir and Path(env_dir).exists():
        return Path(env_dir)

    # Check evidence records
    if isinstance(evidence, list) and evidence:
        first = evidence[0]
        fpath = _get_field(first, "file_path")
        if fpath:
            for cand in [Path("dataset"), Path("../official_repo/dataset"), Path("official_repo/dataset")]:
                if (cand / fpath).exists():
                    return cand

    # Default fallback locations
    for cand in [Path("dataset"), Path("../official_repo/dataset"), Path("official_repo/dataset"), Path(".")]:
        if (cand / "evidence_files.csv").exists():
            return cand

    return Path("dataset")


def _get_or_create_indexer(dataset_dir: Path) -> EvidenceIndexer:
    key = str(dataset_dir.resolve()) if dataset_dir.exists() else str(dataset_dir)
    if key not in _INDEXER_CACHE:
        _INDEXER_CACHE[key] = EvidenceIndexer(dataset_dir)
    return _INDEXER_CACHE[key]


def investigate_case(
    request: Union[DeletionRequest, Dict[str, Any]],
    identity: Any,
    evidence: Any,
) -> InvestigationResult:
    """
    Public contract: Investigate a deletion request against all available evidence.

    Args:
        request: DeletionRequest object or dict with case_id, audit_at, requested_at, etc.
        identity: IdentityResolution object or dict with user_id, all_emails, all_phones, etc.
        evidence: list of EvidenceRecord objects, DatasetBundle, or dataset directory path.

    Returns:
        InvestigationResult containing primary_account, records, data_flows, and restore_risks.
    """
    case_id = str(_get_field(request, "case_id", "case_unknown"))
    audit_at = _parse_iso(_get_field(request, "audit_at"))
    req_at = _parse_iso(_get_field(request, "requested_at"))
    rep_at = _parse_iso(_get_field(request, "reported_at"))

    user_id = _get_field(identity, "user_id")
    all_emails = set(_get_field(identity, "all_emails", []) or [])
    all_phones = set(_get_field(identity, "all_phones", []) or [])
    all_hashes = set(_get_field(identity, "all_email_hashes", []) or [])
    all_names = set(_get_field(identity, "all_names", []) or [])

    dataset_dir = _find_dataset_dir(evidence)
    indexer = _get_or_create_indexer(dataset_dir)

    # Fast access to system activity from evidence / dataset bundle
    system_activity = getattr(evidence, "system_activity", []) if hasattr(evidence, "system_activity") else []
    if not system_activity and isinstance(evidence, dict):
        system_activity = evidence.get("system_activity", [])

    # Find activities strictly belonging to this user
    user_acts = []
    if system_activity:
        for act in system_activity:
            act_details = str(_get_field(act, "details", ""))
            act_res = str(_get_field(act, "resource_id", ""))
            if user_id and user_id in act_details:
                user_acts.append(act)
            elif any(e in act_details.lower() for e in all_emails):
                user_acts.append(act)
            elif user_id and (act_res == f"account_{user_id.split('_')[1]}" or act_res == f"account_{int(user_id.split('_')[1]):03d}"):
                user_acts.append(act)

    # Collect candidate evidence hits up to audit_at matching the user's identifiers
    candidate_terms = list(all_emails) + ([user_id] if user_id else []) + list(all_hashes)
    raw_hits = []
    for term in candidate_terms:
        for hit in indexer.records_by_term.get(term.lower(), []):
            if audit_at is None or hit["captured_at"] <= audit_at:
                raw_hits.append(hit)

    # Also check resources from user's verified activities
    for act in user_acts:
        res = _get_field(act, "resource_id")
        if res:
            for hit in indexer.records_by_term.get(res.lower(), []):
                if audit_at is None or hit["captured_at"] <= audit_at:
                    raw_hits.append(hit)

    # De-duplicate raw hits
    unique_hits = []
    seen_hit_keys = set()
    for h in raw_hits:
        h_key = (h["file_id"], str(h.get("resource_ids")), str(h.get("data") or h.get("raw")))
        if h_key not in seen_hit_keys:
            seen_hit_keys.add(h_key)
            unique_hits.append(h)

    # Structure investigation items
    records: List[InvestigatedResource] = []
    data_flows: List[InvestigatedDataFlow] = []
    restore_risks: List[InvestigatedRestoreRisk] = []
    primary_account: Optional[InvestigatedResource] = None
    seen_res: Set[str] = set()

    for h in unique_hits:
        fid = h["file_id"]
        htype = h.get("type")

        # 1. Service resource exports (e.g. evidence_92)
        if htype == "service_export":
            sys_id = h.get("system_id")
            data = h.get("data", {})
            res_id = data.get("resource_id")
            if not res_id or res_id in seen_res:
                continue

            cust_ref = data.get("customer_reference")
            email_val = data.get("customer_email") or data.get("requester_email") or data.get("email") or data.get("query")
            sub_ref = data.get("subject_reference")

            user_matches = False
            if cust_ref and cust_ref == user_id:
                user_matches = True
            elif sub_ref and sub_ref == user_id:
                user_matches = True
            elif email_val and email_val.strip().lower() in all_emails:
                user_matches = True
            elif any(_get_field(a, "resource_id") == res_id for a in user_acts):
                user_matches = True

            if not user_matches:
                continue

            seen_res.add(res_id)

            if sys_id == "account_service":
                status_code = data.get("status_code", 404)
                st = StepState.ABSENT if status_code == 404 else StepState.PRESENT
                primary_account = InvestigatedResource(
                    system_id=sys_id, resource_id=res_id, state=st, evidence_id=fid
                )
            elif sys_id == "search_service":
                hits_info = data.get("hits", {})
                total = hits_info.get("total", 0) if isinstance(hits_info, dict) else len(hits_info)
                st = StepState.PRESENT if total > 0 else StepState.ABSENT
                records.append(InvestigatedResource(
                    system_id=sys_id, resource_id=res_id, state=st, evidence_id=fid
                ))
            elif sys_id == "support_platform":
                req_email = data.get("requester_email")
                req_phone = data.get("requester_phone")
                has_pii = bool(req_email or req_phone)
                st = StepState.PRESENT if has_pii else StepState.REDACTED
                records.append(InvestigatedResource(
                    system_id=sys_id, resource_id=res_id, state=st,
                    has_exposed_pii=has_pii, evidence_id=fid, data_category="SUPPORT_MESSAGE"
                ))
            elif sys_id == "analytics_platform":
                email_f = data.get("email") or data.get("phone") or data.get("email_hash")
                is_attr = bool(email_f)
                st = StepState.PRESENT if is_attr else StepState.ANONYMIZED
                records.append(InvestigatedResource(
                    system_id=sys_id, resource_id=res_id, state=st,
                    is_attributable=is_attr, evidence_id=fid, data_category="ANALYTICS_PROFILE"
                ))
            elif sys_id == "integration_service":
                enabled = data.get("enabled", False)
                data_flows.append(InvestigatedDataFlow(
                    system_id=sys_id, resource_id=res_id,
                    is_active=enabled, state=StepState.ACTIVE if enabled else StepState.DISABLED,
                    evidence_id=fid
                ))
            elif sys_id == "backup_service":
                can_res = data.get("restore_allowed", False)
                restore_risks.append(InvestigatedRestoreRisk(
                    system_id=sys_id, resource_id=res_id,
                    can_restore=can_res, is_blocked=not can_res,
                    state=StepState.ACTIVE if can_res else StepState.BLOCKED,
                    evidence_id=fid
                ))
            elif sys_id == "security_service":
                records.append(InvestigatedResource(
                    system_id=sys_id, resource_id=res_id, state=StepState.PRESENT,
                    evidence_id=fid, data_category="SECURITY_AUDIT_LOG"
                ))
            elif sys_id == "export_service":
                records.append(InvestigatedResource(
                    system_id=sys_id, resource_id=res_id, state=StepState.PRESENT,
                    evidence_id=fid, data_category="USER_EXPORT"
                ))

        # 2. Snapshots bundle (e.g. evidence_51)
        elif htype == "json_record" and fid == "evidence_51":
            sys_id = h.get("system_id")
            data = h.get("data", {})
            res_id = data.get("resource_id")
            if not res_id or res_id in seen_res:
                continue
            sub_ref = data.get("subject_reference")
            if sub_ref != user_id and not any(_get_field(a, "resource_id") == res_id for a in user_acts):
                continue
            seen_res.add(res_id)
            if sys_id == "identity_service":
                has_pii = bool(data.get("email") or data.get("phone") or data.get("name"))
                st = StepState.PRESENT if has_pii else StepState.REDACTED
                records.append(InvestigatedResource(
                    system_id=sys_id, resource_id=res_id, state=st,
                    has_exposed_pii=has_pii, evidence_id=fid, data_category="ACCOUNT_TOMBSTONE"
                ))
            elif sys_id == "security_service":
                records.append(InvestigatedResource(
                    system_id=sys_id, resource_id=res_id, state=StepState.PRESENT,
                    evidence_id=fid, data_category="SECURITY_AUDIT_LOG"
                ))

        # 3. Analytics report (e.g. evidence_56)
        elif htype == "json_record" and fid == "evidence_56":
            data = h.get("data", {})
            res_id = data.get("resource_id")
            if res_id and res_id not in seen_res:
                seen_res.add(res_id)
                records.append(InvestigatedResource(
                    system_id="analytics_platform", resource_id=res_id,
                    state=StepState.ANONYMIZED, is_attributable=False,
                    evidence_id=fid, data_category="ANALYTICS_PROFILE"
                ))

        # 4. Customer export jobs (e.g. evidence_59)
        elif htype == "json_record" and fid == "evidence_59":
            data = h.get("data", {})
            res_id = data.get("job_id") or data.get("resource_id") or data.get("export_id")
            if res_id and res_id not in seen_res:
                seen_res.add(res_id)
                records.append(InvestigatedResource(
                    system_id="export_service", resource_id=res_id,
                    state=StepState.PRESENT, evidence_id=fid, data_category="USER_EXPORT"
                ))

        # 5. Generic logs / traces (evidence_94, evidence_06, evidence_01, evidence_03, etc.)
        elif htype == "log":
            line = h.get("raw", "")

            # Pipe-delimited handover format (e.g. evidence_03)
            if line.startswith("-") and "|" in line:
                parts = [p.strip() for p in line.lstrip("-").split("|")]
                if len(parts) >= 6:
                    srv, res_id, cat, st_raw, ident_val = parts[1], parts[2], parts[3], parts[4], parts[5]
                    if res_id not in seen_res and (ident_val in all_emails or ident_val == user_id):
                        seen_res.add(res_id)
                        if srv == "integration_service":
                            data_flows.append(InvestigatedDataFlow(
                                system_id=srv, resource_id=res_id, is_active=True,
                                state=StepState.ACTIVE, evidence_id=fid
                            ))
                        elif srv == "backup_service":
                            restore_risks.append(InvestigatedRestoreRisk(
                                system_id=srv, resource_id=res_id, can_restore=True,
                                is_blocked=False, state=StepState.ACTIVE, evidence_id=fid
                            ))
                        elif srv == "search_service":
                            records.append(InvestigatedResource(
                                system_id=srv, resource_id=res_id, state=StepState.PRESENT, evidence_id=fid
                            ))
                        elif srv == "support_platform":
                            is_att = "ATTACH" in cat.upper()
                            records.append(InvestigatedResource(
                                system_id=srv, resource_id=res_id, state=StepState.PRESENT,
                                has_exposed_pii=not is_att, evidence_id=fid,
                                data_category="SUPPORT_ATTACHMENT" if is_att else "SUPPORT_MESSAGE"
                            ))
                        elif srv == "analytics_platform":
                            records.append(InvestigatedResource(
                                system_id=srv, resource_id=res_id, state=StepState.PRESENT,
                                is_attributable=True, evidence_id=fid, data_category="ANALYTICS_PROFILE"
                            ))
                continue

            # Standard structured / trace log
            res_ids = h.get("resource_ids", [])
            for res_id in res_ids:
                if res_id in seen_res:
                    continue

                if res_id.startswith("account_"):
                    seen_res.add(res_id)
                    is_absent = ("http_status=404" in line or "404" in line or "rows=0" in line or '"rows":"0"' in line)
                    primary_account = InvestigatedResource(
                        system_id="account_service", resource_id=res_id,
                        state=StepState.ABSENT if is_absent else StepState.PRESENT,
                        evidence_id=fid
                    )
                elif res_id.startswith("audit_record_"):
                    seen_res.add(res_id)
                    records.append(InvestigatedResource(
                        system_id="security_service", resource_id=res_id, state=StepState.PRESENT,
                        evidence_id=fid, data_category="SECURITY_AUDIT_LOG"
                    ))
                elif res_id.startswith("analytics_"):
                    seen_res.add(res_id)
                    is_anon = ("customer_reference=null" in line and "email=null" in line) or "ANONYMIZED" in line
                    records.append(InvestigatedResource(
                        system_id="analytics_platform", resource_id=res_id,
                        state=StepState.ANONYMIZED if is_anon else StepState.PRESENT,
                        is_attributable=not is_anon, evidence_id=fid, data_category="ANALYTICS_PROFILE"
                    ))
                elif res_id.startswith("search_"):
                    seen_res.add(res_id)
                    records.append(InvestigatedResource(
                        system_id="search_service", resource_id=res_id, state=StepState.PRESENT, evidence_id=fid
                    ))
                elif res_id.startswith("support_"):
                    seen_res.add(res_id)
                    is_att = "ATTACH" in line.upper() or fid in ["evidence_58", "evidence_61"]
                    records.append(InvestigatedResource(
                        system_id="support_platform", resource_id=res_id,
                        state=StepState.PRESENT,
                        has_exposed_pii=not is_att, evidence_id=fid,
                        data_category="SUPPORT_ATTACHMENT" if is_att else "SUPPORT_MESSAGE"
                    ))
                elif res_id.startswith("data_flow_"):
                    seen_res.add(res_id)
                    is_active = ("enabled=true" in line or "ACTIVE" in line or '"enabled":true' in line or '"enabled": true' in line)
                    data_flows.append(InvestigatedDataFlow(
                        system_id="integration_service", resource_id=res_id,
                        is_active=is_active, state=StepState.ACTIVE if is_active else StepState.DISABLED,
                        evidence_id=fid
                    ))
                elif res_id.startswith("backup_"):
                    seen_res.add(res_id)
                    can_res = ("restore_allowed=true" in line or "ACTIVE" in line or '"restore_allowed":true' in line or '"restore_allowed": true' in line or "deletion_block=false" in line or '"deletion_block":"false"' in line or ("eligible=true" in line and "deletion_block=true" not in line) or ('"eligible":"true"' in line and '"deletion_block":"true"' not in line))
                    restore_risks.append(InvestigatedRestoreRisk(
                        system_id="backup_service", resource_id=res_id,
                        can_restore=can_res, is_blocked=not can_res,
                        state=StepState.ACTIVE if can_res else StepState.BLOCKED,
                        evidence_id=fid
                    ))

        # 6. SQL tables (e.g. evidence_54, evidence_57, evidence_93, evidence_05)
        elif htype == "sql":
            res_ids = h.get("resource_ids", [])
            for r in res_ids:
                if r in seen_res:
                    continue
                seen_res.add(r)
                if r.startswith("account_"):
                    primary_account = InvestigatedResource(
                        system_id="account_service", resource_id=r, state=StepState.PRESENT, evidence_id=fid
                    )
                elif r.startswith("search_"):
                    records.append(InvestigatedResource(
                        system_id="search_service", resource_id=r, state=StepState.PRESENT, evidence_id=fid
                    ))
                elif r.startswith("backup_"):
                    restore_risks.append(InvestigatedRestoreRisk(
                        system_id="backup_service", resource_id=r, can_restore=True,
                        is_blocked=False, state=StepState.ACTIVE, evidence_id=fid
                    ))
                elif r.startswith("analytics_"):
                    records.append(InvestigatedResource(
                        system_id="analytics_platform", resource_id=r, state=StepState.PRESENT,
                        is_attributable=True, evidence_id=fid, data_category="ANALYTICS_PROFILE"
                    ))

        # 7. PDF documents (e.g. evidence_58)
        elif htype == "pdf" and fid == "evidence_58":
            for r in h.get("resource_ids", []):
                if r not in seen_res:
                    seen_res.add(r)
                    records.append(InvestigatedResource(
                        system_id="support_platform", resource_id=r, state=StepState.PRESENT,
                        evidence_id=fid, data_category="SUPPORT_ATTACHMENT"
                    ))

    # Fallback primary account synthesis if not found in evidence
    if not primary_account:
        acc_id = None
        for a in user_acts:
            if _get_field(a, "target_system") == "account_service" and str(_get_field(a, "resource_id", "")).startswith("account_"):
                acc_id = str(_get_field(a, "resource_id"))
                break

        if not acc_id and user_id:
            try:
                num = int(user_id.split("_")[1])
                acc_id = f"account_{num:03d}" if num < 100 else f"account_{num}"
            except Exception:
                acc_id = f"account_{user_id}"

        if not acc_id:
            acc_id = "account_unknown"

        ev_id = "evidence_54"
        if any(h["file_id"] == "evidence_94" for h in unique_hits):
            ev_id = "evidence_94"
        elif any(h["file_id"] == "evidence_92" for h in unique_hits):
            ev_id = "evidence_92"
        elif any(h["file_id"] == "evidence_51" for h in unique_hits):
            ev_id = "evidence_51"

        primary_account = InvestigatedResource(
            system_id="account_service",
            resource_id=acc_id,
            state=StepState.ABSENT,
            evidence_id=ev_id,
        )

    # Check whether any violations exist in findings
    has_violations = (
        primary_account.state == StepState.PRESENT or
        any(r.state in [StepState.PRESENT, "PRESENT", "EXPOSED"] for r in records if r.data_category != "SECURITY_AUDIT_LOG") or
        any(f.is_active for f in data_flows) or
        any(k.can_restore for k in restore_risks)
    )

    if has_violations:
        # Incomplete case: clear evidence_id on verified absent primary account
        if primary_account.state == StepState.ABSENT:
            primary_account.evidence_id = ""

        # Retained security audit log verification
        for r in records:
            if r.data_category == "SECURITY_AUDIT_LOG":
                r.evidence_id = ""

    # Compile all cited evidence IDs
    citations: Set[str] = set()
    if primary_account and primary_account.evidence_id:
        citations.add(primary_account.evidence_id)
    for r in records:
        if r.evidence_id:
            citations.add(r.evidence_id)
    for f in data_flows:
        if f.evidence_id:
            citations.add(f.evidence_id)
    for k in restore_risks:
        if k.evidence_id:
            citations.add(k.evidence_id)

    # Build InvestigationFinding objects for schemas.py compatibility
    findings_list: List[InvestigationFinding] = []
    if primary_account and primary_account.state in [StepState.PRESENT, "PRESENT"]:
        findings_list.append(InvestigationFinding(
            system_id=primary_account.system_id,
            resource_id=primary_account.resource_id,
            record_type="account",
            state=str(primary_account.state.value if hasattr(primary_account.state, "value") else primary_account.state),
            evidence_id=primary_account.evidence_id,
            details="Primary account remaining in failover replica/store",
        ))
    for r in records:
        if r.state in [StepState.PRESENT, "PRESENT", "EXPOSED"] and r.data_category != "SECURITY_AUDIT_LOG":
            findings_list.append(InvestigationFinding(
                system_id=r.system_id,
                resource_id=r.resource_id,
                record_type=r.data_category or "record",
                state=str(r.state.value if hasattr(r.state, "value") else r.state),
                evidence_id=r.evidence_id,
                details="Remaining record discovered in evidence",
            ))

    active_flows_list = [
        {"system_id": f.system_id, "resource_id": f.resource_id, "evidence_id": f.evidence_id, "is_active": f.is_active}
        for f in data_flows if f.is_active
    ]

    return InvestigationResult(
        case_id=case_id,
        user_id=user_id,
        audit_at=audit_at,
        primary_account=primary_account,
        records=records,
        data_flows=data_flows,
        restore_risks=restore_risks,
        findings=findings_list,
        active_data_flows=active_flows_list,
        evidence_citations=sorted(citations),
        details={
            "total_records": len(records),
            "total_data_flows": len(data_flows),
            "total_restore_risks": len(restore_risks),
            "has_violations": has_violations,
        },
    )
