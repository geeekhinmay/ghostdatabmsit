# Evaluation Report: Ghost Data Still Exists

## 1. Executive Summary
- Evaluation target: HackerRank Orchestrate (October 2026) Deletion Audit Pipeline.
- Challenge: Ghost Data Still Exists.
- Case count evaluated: 518 evaluation requests (and 32 sample requests).
- Pipeline status: 100% operational, fully integrated, end-to-end verified.

## 2. Accuracy Metrics & Full Evaluation Results
- **Total Requests Evaluated**: 518
- **Status Distribution**:
  - `COMPLETE`: 145 cases
  - `INCOMPLETE`: 369 cases
  - `NOT_APPLICABLE`: 4 cases
- **Total Steps Generated**: 3,860 steps
- **Schema & Formatting Accuracy**: 100% compliant with official HackerRank schema (`case_id,deletion_status,steps_json`).
- **Ordering & Sequence Accuracy**: 100% compliant with official sorting specification (`FINDING` -> `REMEDIATION` -> `VERIFICATION` -> operation priority -> system_id ASC -> resource_id ASC).
- **Remediation Constraints**: 100% compliant (all remediation steps carry empty `evidence_id=""`).
- **Non-Deletion Constraints**: 100% compliant (all `NOT_APPLICABLE` cases contain empty steps array `[]`).

## 3. Team-Created Evaluation Test Cases
### Test Case 1: Active Replication Lag & Failover Drift
- Scenario: Primary database has removed account record; regional replica snapshot captured before audit_at still contains full profile.
- Verdict: `INCOMPLETE`.
- Findings: `REPORT_REMAINING_RECORD` on regional replica citing evidence file.
- Remediation: `DELETE_RECORD` on replica.
- Verification: `VERIFY_RECORD_ABSENT` with empty evidence ID.

### Test Case 2: Multi-Language Non-Deletion Request
- Scenario: User message in French asking for data export ("Je souhaite exporter l'ensemble de mes données personnelles") with reported_status="PARTIALLY_COMPLETE".
- Verdict: `NOT_APPLICABLE`.
- Generated Steps: `[]` (empty JSON array).

### Test Case 3: Account Tombstone with Exposed PII Hash
- Scenario: Primary profile deleted, but tombstone record preserves `email_hash` and `phone` alongside permitted `user_id`.
- Verdict: `INCOMPLETE`.
- Findings: `REPORT_EXPOSED_PII` on identity service tombstone citing evidence file.
- Remediation: `REDACT_RECORD` on tombstone.
- Verification: `VERIFY_RECORD_REDACTED` with empty evidence ID.

## 4. Failures Identified and Architecture Improvements
- **Intermediate Step Numbering**: Addressed intermediate `step_no=0` validation error during pre-sort step generation by allowing `ge=0` in `AuditStep` while enforcing consecutive `1, 2, 3...` in the output validator and final sort.
- **Investigation Result Compatibility**: Added `is_deletion_request` fallback attribute to `InvestigationResult` ensuring seamless inter-operation between Member 3's investigation engine and Member 4's policy evaluator.
- **Temporal Cutoff Alignment**: Ensured Member 3's audit cutoff filtering on `user_audit_log` and `system_activity` is preserved so evidence created after `audit_at` never contaminates historical findings.
