# Investigation Module (Owned by Member 3)

## Assigned Role
Member 3 owns case investigation and evidence correlation.

## Public Function Contract
```python
from code.models.schemas import DeletionRequest, IdentityResolution, DatasetBundle, InvestigationResult

def investigate_case(
    request: DeletionRequest,
    identity: IdentityResolution,
    evidence: DatasetBundle,
) -> InvestigationResult:
    """Investigate evidence up to audit_at timestamp and produce an InvestigationResult."""
    ...
```

## Crucial Requirements
1. Determine whether `request_text` actually authorizes deletion (set `is_deletion_request = False` if not).
2. Filter evidence strictly up to `request.audit_at`. Do not consider evidence captured after `audit_at`.
3. Report findings with valid participant-visible evidence IDs (`file_id`, `activity_id`, or `audit_id`).
4. Allowed operations in findings:
   - `REPORT_REMAINING_RECORD` (state: `PRESENT`)
   - `REPORT_EXPOSED_PII` (state: `PRESENT`)
   - `REPORT_ACTIVE_DATA_FLOW` (state: `ACTIVE`)
   - `REPORT_RESTORE_RISK` (state: `ACTIVE`)
