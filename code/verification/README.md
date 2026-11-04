# Verification Module

**Owner:** Member 4 (Hrushikesh)  
**Package:** `code.verification`

## Overview

The verification module generates verification checks:
1. For `COMPLETE` cases: evidence-backed verification steps that prove every copy was handled correctly, retained records remain present, and sync/restore paths are blocked at `audit_at`. Each step cites a valid participant-visible `evidence_id`.
2. For `INCOMPLETE` cases: post-remediation verification checks that confirm every remediated item achieves its intended final state, alongside verification of primary account deletion and retained records. All steps use `evidence_id = ""`.

Follows the official verification operation order:
1. `VERIFY_RECORD_ABSENT`
2. `VERIFY_RECORD_PRESENT`
3. `VERIFY_RECORD_REDACTED`
4. `VERIFY_RECORD_ANONYMIZED`
5. `VERIFY_DATA_FLOW_DISABLED`
6. `VERIFY_RESTORE_BLOCKED`
followed by `system_id` ASC and `resource_id` ASC.

## Public Interface

```python
from code.verification import build_verification_steps

verification_steps: list[AuditStep] = build_verification_steps(request, investigation, policy)
```

### Parameters
- `request`: `DeletionRequest` object or dict.
- `investigation`: `InvestigationResult` object or dict.
- `policy`: `PolicyDecision` object or dict returned by `evaluate_policy`.

### Return Value
`list[AuditStep]`: Ordered verification steps with `phase="VERIFICATION"`. Empty for `NOT_APPLICABLE` cases.

## Integration Example

```python
from code.policy import evaluate_policy
from code.remediation import build_remediation_plan
from code.verification import build_verification_steps

policy = evaluate_policy(request, investigation, rules)
remediation_steps = build_remediation_plan(request, investigation, policy)
verification_steps = build_verification_steps(request, investigation, policy)

# Full steps for case output:
all_steps = policy.findings + remediation_steps + verification_steps
```
