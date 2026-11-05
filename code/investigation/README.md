# Investigation Module (`code/investigation/`)

**Owned by**: Member 3 — Chirag Gowda (`chirag.gowda@example.com`)  
**Role**: Identity Resolution and Evidence Investigation Engineer

---

## 1. Overview

The `code/investigation/` module investigates individual personal data deletion cases across participant-visible evidence files, discovering whether customer data was fully expunged, redacted, or anonymized, or if residual records, active data flows, or backup restore risks remain.

### Key Capabilities:
- **Strict Temporal Filtering**: Only inspects evidence captured at or before the case's `audit_at` cutoff timestamp (`captured_at <= audit_at`), ignoring post-audit artifacts.
- **Decoy & Unrelated Record Rejection**: Discerns decoys and unrelated records by strictly requiring linkage to the subject's identity cluster (`user_id`, historical emails, phone numbers, or email hashes).
- **Multi-System Coverage**:
  - `account_service`: Detects primary account state, verifying 404/absent status or un-deleted replica drift.
  - `search_service`: Discovers residual search index documents.
  - `support_platform`: Distinguishes support attachments (requiring deletion) from shared support messages (requiring redaction).
  - `analytics_platform`: Identifies unlinked anonymized profiles vs attributable analytics records.
  - `integration_service`: Uncovers active data flows, sync bridges, and enabled connectors.
  - `backup_service`: Discovers restorable backup archives and verifies blocked restore paths.
  - `identity_service`: Distinguishes redacted tombstones from tombstones with exposed PII.
  - `security_service`: Audits lawfully retained security audit logs.
  - `export_service`: Discovers leftover user export archives.

---

## 2. Public Contract

```python
def investigate_case(
    request: Union[DeletionRequest, Dict[str, Any]],
    identity: IdentityResolution,
    evidence: Union[List[EvidenceRecord], DatasetBundle, Any],
) -> InvestigationResult:
```

### Parameters:
- `request`: The deletion request object containing `case_id`, `audit_at`, `requested_at`, and `reported_at`.
- `identity`: The resolved `IdentityResolution` object from `resolve_identity(request, dataset)`.
- `evidence`: The collection of parsed `EvidenceRecord` objects or `DatasetBundle`.

### Returns:
- `InvestigationResult`: Contains `primary_account`, `records`, `data_flows`, `restore_risks`, and `evidence_citations`.

---

## 3. Integration Example

```python
from code.ingestion.loader import load_dataset
from code.ingestion.evidence import parse_all_evidence
from code.identity import resolve_identity
from code.investigation import investigate_case
from code.policy.evaluator import evaluate_policy

dataset = load_dataset("dataset/")
evidence = parse_all_evidence("dataset/", dataset.evidence_manifest)

request = dataset.deletion_requests[0]
identity = resolve_identity(request, dataset)
investigation = investigate_case(request, identity, evidence)

print(f"Investigated case: {investigation.case_id}")
print(f"Primary account state: {investigation.primary_account.state}")
print(f"Records discovered: {len(investigation.records)}")
print(f"Active data flows: {len(investigation.data_flows)}")
print(f"Restore risks: {len(investigation.restore_risks)}")

# Downstream consumption by Member 4:
policy_decision = evaluate_policy(request, investigation, dataset.deletion_rules)
```

