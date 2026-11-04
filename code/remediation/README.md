# Remediation Planning Module (Owned by Member 4)

## Assigned Role
Member 4 owns generating safe, ordered remediation steps for incomplete cases.

## Public Function Contract
```python
from code.models.schemas import DeletionRequest, InvestigationResult, PolicyDecision, Step

def build_remediation_plan(
    request: DeletionRequest,
    investigation: InvestigationResult,
    policy: PolicyDecision,
) -> list[Step]:
    """Generate ordered remediation steps for an INCOMPLETE case."""
    ...
```

## Crucial Requirements
1. Allowed remediation operations and required states:
   - `DISABLE_DATA_FLOW` -> `DISABLED`
   - `BLOCK_RESTORE` -> `BLOCKED`
   - `DELETE_RECORD` -> `ABSENT`
   - `REDACT_RECORD` -> `REDACTED`
   - `ANONYMIZE_RECORD` -> `ANONYMIZED`
2. Future remediation steps must have `evidence_id = ""`.
3. Order: Stop active flows and block restores before modifying dependent records.
