# Evaluation Report: Ghost Data Still Exists

## 1. Executive Summary
- Evaluation target: HackerRank Orchestrate (October 2026) Deletion Audit Pipeline.
- Challenge: Ghost Data Still Exists.
- Case count evaluated: 518 evaluation requests (and 32 sample requests).
- Pipeline status: 100% operational, fully integrated, end-to-end verified with 32/32 sample agreement.

## 2. Accuracy Metrics & Full Evaluation Results
- **Total Requests Evaluated**: 518
- **Status Distribution**:
  - `COMPLETE`: 144 cases
  - `INCOMPLETE`: 370 cases
  - `NOT_APPLICABLE`: 4 cases
- **Total Steps Generated**: 3,864 steps
- **Sample Mode Status Agreement**: **32 / 32** (100% match against official `sample_output.csv`)
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
- **Intent Pattern Extension**: Extended `DELETION_PATTERNS` in `code/policy/intent.py` to recognize requests asking to verify that a profile or account "is gone" (resolving `case_26` from `NOT_APPLICABLE` to `COMPLETE`).
- **Backup Log Semantics**: Enhanced backup log parsing in `code/investigation/investigator.py` to identify `deletion_block=false` as an active restore risk (resolving `case_17` from `COMPLETE` to `INCOMPLETE`).
- **Temporal Datetime Typing**: Strictly typed `audit_at: datetime` on `DeletionRequest` in `code/models/schemas.py`, enabling native timezone-aware comparisons against `EvidenceFileEntry.captured_at` across all sample alignment tests.
