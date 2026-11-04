# Verification Module (Owned by Member 4)

## Assigned Role
Member 4 owns generating verification steps proving compliance.

## Public Function Contract
```python
from code.models.schemas import DeletionRequest, InvestigationResult, PolicyDecision, Step

def build_verification_steps(
    request: DeletionRequest,
    investigation: InvestigationResult,
    policy: PolicyDecision,
) -> list[Step]:
    """Generate verification checks.
    
    - For COMPLETE cases: verification steps must cite valid evidence_id proving the state at audit_at.
    - For INCOMPLETE cases: verification steps describe future checks after remediation and must have evidence_id = "".
    """
    ...
```

## Crucial Requirements
1. Allowed operations and states:
   - `VERIFY_RECORD_ABSENT` -> `ABSENT`
   - `VERIFY_RECORD_PRESENT` -> `PRESENT`
   - `VERIFY_RECORD_REDACTED` -> `REDACTED`
   - `VERIFY_RECORD_ANONYMIZED` -> `ANONYMIZED`
   - `VERIFY_DATA_FLOW_DISABLED` -> `DISABLED`
   - `VERIFY_RESTORE_BLOCKED` -> `BLOCKED`
2. Never cite evidence captured after `request.audit_at`.
