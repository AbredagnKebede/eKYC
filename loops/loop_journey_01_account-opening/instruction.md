# Journey Loop: loop_journey_01_account-opening
journey_file: journeys/journey_01_account-opening.md
covers: AS-01
priority: critical

## Objective
This journey loop proves end-to-end functionality for `journeys/journey_01_account-opening.md`.
It adds NO NEW production behavior: its sole purpose is black-box verification of what the component loops built against a real running system.

## Assertion Points to Prove
- AP-1 Database: applications table row has status='ACCOUNT_OPENED' and non-null idempotency_hash
- AP-2 Database: identity_snapshots table row has verification_method='OTP' and encrypted demographics
- AP-3 Queue: bank_submission_queue message was consumed and acknowledged by bank_submission_worker
- AP-4 External API: fayda_ekyc_api sandbox received verification request and returned HTTP 200 with verified claims
- AP-5 External API: bank_cbs_api sandbox received verified submission payload and returned a generated account number
- AP-6 Audit: audit_logs table contains hash-chained entries for CONSENT_GRANTED, IDENTITY_VERIFIED, LIVENESS_PASSED, and APPLICATION_SUBMITTED
- AP-7 Latency: Complete application submission to account issuance round-trip completes within 5.0 seconds

## Boundaries & Environment
- Real boundaries: `db, queue, external_api, worker`
- Services running: `postgres redis fayda-sandbox cbs-sandbox worker api`
- Required credentials: `FAYDA_API_KEY BANK_API_KEY`
