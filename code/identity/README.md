# Identity Resolution Module (Owned by Member 3)

## Assigned Role
Member 3 owns identity resolution and case investigation.

## Public Function Contract
```python
from code.models.schemas import DeletionRequest, DatasetBundle, IdentityResolution

def resolve_identity(request: DeletionRequest, dataset: DatasetBundle) -> IdentityResolution:
    """Resolve current and historical identities (emails, names, phones, hashes) for a given case."""
    ...
```

## Shared Schemas
Import `IdentityResolution` from `code.models.schemas`.
Key fields in `IdentityResolution`:
- `case_id: str`
- `user_id: str | None`
- `current_name: str | None`
- `current_email: str | None`
- `current_phone: str | None`
- `current_hash: str | None`
- `all_emails: set[str]`
- `all_names: set[str]`
- `all_phones: set[str]`
- `all_hashes: set[str]`
- `audit_history: list[UserAuditRecord]`
