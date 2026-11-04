# Policy Evaluation Module

**Owner:** Member 4 (Hrushikesh)  
**Package:** `code.policy`

## Overview

The policy evaluation module is responsible for:
1. Classifying customer requests to verify whether they actually authorise personal data deletion or represent non-deletion requests (access requests, export requests, rectification requests, marketing opt-outs, or general inquiries).
2. Applying official policy rules (`deletion_rules.csv`) to every investigated record, data flow, and restore risk.
3. Determining the case-level deletion status (`COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`).
4. Generating ordered findings for incomplete cases according to the official ordering specifications.

## Public Interface

```python
from code.policy import evaluate_policy, PolicyDecision

decision: PolicyDecision = evaluate_policy(request, investigation, rules)
```

### Parameters
- `request`: A `DeletionRequest` instance or dictionary with `case_id` and `request_text`.
- `investigation`: An `InvestigationResult` instance or dictionary with discovered `records`, `data_flows`, and `restore_risks`.
- `rules`: List or dictionary of `DeletionRule` instances (or `DatasetBundle.deletion_rules`).

### Return Value
`PolicyDecision`:
- `case_id: str`: The case identifier.
- `is_deletion_request: bool`: False if request was non-deletion (e.g. SAR, export, opt-out).
- `deletion_status: DeletionStatus`: `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`.
- `findings: list[AuditStep]`: Ordered findings (`REPORT_REMAINING_RECORD`, `REPORT_EXPOSED_PII`, `REPORT_ACTIVE_DATA_FLOW`, `REPORT_RESTORE_RISK`) citing participant evidence IDs.
- `remediation_items: list[dict]`: Internal list of needed remediation actions for Member 4 planner.
- `verification_items: list[dict]`: Internal list of compliant records/checks for Member 4 verifier.

## Integration Example

```python
from code.models.schemas import DeletionRequest
from code.policy import evaluate_policy

# Call evaluate_policy
decision = evaluate_policy(request, investigation, rules)

if decision.deletion_status == DeletionStatus.NOT_APPLICABLE:
    # Non-deletion request -> output steps_json = []
    final_steps = []
else:
    # Incomplete or complete case -> proceed to remediation and verification
    pass
```
