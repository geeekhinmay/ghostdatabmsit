# Remediation Planning Module

**Owner:** Member 4 (Hrushikesh)  
**Package:** `code.remediation`

## Overview

The remediation planning module builds the ordered remediation plan for incomplete deletion cases.
It respects system dependencies:
1. Disabling active data flows (sync/replication) first.
2. Blocking restore risks second.
3. Deleting records third.
4. Redacting records fourth.
5. Anonymizing records fifth.

Within each operation type, items are sorted by `system_id` ASC, then `resource_id` ASC. All proposed remediation steps cite `evidence_id = ""`.

## Public Interface

```python
from code.remediation import build_remediation_plan

remediation_steps: list[AuditStep] = build_remediation_plan(request, investigation, policy)
```

### Parameters
- `request`: `DeletionRequest` object or dict.
- `investigation`: `InvestigationResult` object or dict.
- `policy`: `PolicyDecision` object or dict returned by `evaluate_policy`.

### Return Value
`list[AuditStep]`: Ordered remediation steps with `phase="REMEDIATION"` and `evidence_id=""`. Empty for `COMPLETE` or `NOT_APPLICABLE` cases.

## Integration Example

```python
from code.policy import evaluate_policy
from code.remediation import build_remediation_plan

policy = evaluate_policy(request, investigation, rules)
remediation_steps = build_remediation_plan(request, investigation, policy)
```
