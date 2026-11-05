# Identity Resolution Module (`code/identity/`)

**Owned by**: Member 3 — Chirag Gowda (`chirag.gowda@example.com`)  
**Role**: Identity Resolution and Evidence Investigation Engineer

---

## 1. Overview

The `code/identity/` module is responsible for resolving the subject of a personal data deletion request to their canonical user identity across current snapshots and historical audit logs.

### Key Capabilities:
- **Case-Insensitive & Normalized Matching**: Safely normalizes incoming email addresses (stripping whitespace and lowercase conversion).
- **Direct Snapshot Resolution**: Resolves active customer profiles in `user_identities.csv`.
- **Historical Identity Resolution**: Resolves users who changed their email address prior to submitting a deletion request by traversing `user_audit_log.csv` records for `email` changes.
- **Identity Clustering**: Aggregates all current and historical identifiers (`all_emails`, `all_phones`, `all_email_hashes`, and `all_names`) into a unified `IdentityResolution` object to empower comprehensive downstream evidence investigation.
- **Auditing & Traceability**: Collects chronologically ordered `UserAuditEntry` logs and associated `SystemActivity` records for the user.

---

## 2. Public Contract

```python
def resolve_identity(
    request: Union[DeletionRequest, Dict[str, Any]],
    dataset: DatasetBundle,
) -> IdentityResolution:
```

### Parameters:
- `request`: A `DeletionRequest` instance or dictionary with at least `case_id` and `email`.
- `dataset`: The `DatasetBundle` loaded by Member 2 (`load_dataset`).

### Returns:
- `IdentityResolution`: Domain model containing `user_id`, `is_identified`, `all_emails`, `all_phones`, `all_email_hashes`, `audit_entries`, and `associated_activities`.

---

## 3. Integration Example

```python
from code.ingestion.loader import load_dataset
from code.identity import resolve_identity

# Load dataset bundle
dataset = load_dataset("dataset/")

# Resolve a deletion request
request = dataset.deletion_requests[0]
identity = resolve_identity(request, dataset)

print(f"Case: {identity.case_id}")
print(f"User ID: {identity.user_id}")
print(f"Identified By: {identity.matched_by}")
print(f"Known Emails: {identity.all_emails}")
print(f"Known Hashes: {identity.all_email_hashes}")
```

