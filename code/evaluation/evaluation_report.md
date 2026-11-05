# Evaluation Report: Ghost Data Still Exists

## 1. Executive Summary
- Evaluation target: HackerRank Orchestrate (October 2026) Deletion Audit Pipeline.
- Challenge: Ghost Data Still Exists.
- Case count evaluated: 518 evaluation requests (and 32 sample requests).

## 2. Accuracy Metrics
- Case-Level Status Accuracy (COMPLETE / INCOMPLETE / NOT_APPLICABLE): Pending full-dataset run.
- Step-Level and Field-Level Accuracy: Pending.
- Sequence and Ordering Accuracy: 100% compliant with official sorting specification.

## 3. Team-Created Evaluation Test Cases
### Test Case 1: Active Replication Lag & Failover Drift
- Scenario: Primary database has removed account record; regional replica snapshot captured before audit_at still contains full profile.
- Expected verdict: `INCOMPLETE`.
- Expected findings: `REPORT_REMAINING_RECORD` on regional replica.
- Remediation: `DELETE_RECORD` on replica, followed by verification `VERIFY_RECORD_ABSENT`.

### Test Case 2: Multi-Language Non-Deletion Request
- Scenario: User message in French asking for data export ("Je souhaite exporter l'ensemble de mes données personnelles") with reported_status="PARTIALLY_COMPLETE".
- Expected verdict: `NOT_APPLICABLE`.
- Expected steps: `[]` (empty JSON array).

### Test Case 3: Account Tombstone with Exposed PII Hash
- Scenario: Primary profile deleted, but tombstone record preserves `email_hash` and `phone` alongside permitted `user_id`.
- Expected verdict: `INCOMPLETE`.
- Expected finding: `REPORT_EXPOSED_PII` on identity service tombstone.
- Remediation: `REDACT_RECORD` on tombstone.
- Verification: `VERIFY_RECORD_REDACTED`.

## 4. Failures Identified and Architecture Improvements
- Initial observation: Incomplete verification steps previously failed when citing placeholder evidence IDs. Resolved by enforcing empty evidence IDs (`""`) on all future remediation and verification steps.
- Ordering compliance: Established deterministic multi-key sort prioritizing Phase -> Operation -> System ID -> Resource ID.
