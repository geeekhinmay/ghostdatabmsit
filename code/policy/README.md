# Policy Module (Owned by Member 4)

## Assigned Role
Member 4 owns policy evaluation, remediation planning, and verification checks.

## Public Function Contract
```python
from code.models.schemas import DeletionRequest, InvestigationResult, DeletionRule, PolicyDecision

def evaluate_policy(
    request: DeletionRequest,
    investigation: InvestigationResult,
    rules: list[DeletionRule],
) -> PolicyDecision:
    """Evaluate applicable deletion rules against investigation findings and return PolicyDecision."""
    ...
```

## Shared Schemas
Import `PolicyDecision` and `DeletionStatus` from `code.models`:
- `DeletionStatus.COMPLETE`: All required deletions, redactions, anonymizations, and tombstone rules satisfied, no active data flows, and no unblocked restore risks.
- `DeletionStatus.INCOMPLETE`: Personal data remains, unredacted PII is exposed, active flows exist, or restore risks exist.
- `DeletionStatus.NOT_APPLICABLE`: The user's request did not authorize deletion.
