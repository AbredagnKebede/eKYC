# Journey: Full End-to-End Self-Service Account Opening
journey_id: J-01
covers: AS-01
priority: critical
graph_nodes: [ui_mobile_app, api_gateway, onboarding_service, identity_service, bank_adapter_service, audit_service, db_postgres, cache_redis, bank_submission_queue, bank_submission_worker, application_submitted_event, fayda_ekyc_api, bank_cbs_api]

## User Steps (black-box perspective)

1. User launches the mobile app, selects English language, and chooses "Awash Bank" from the available partner banks list.
2. User reviews the plain-language consent screen detailing data usage with Fayda and bank sharing, and taps "Agree and Continue".
3. User enters their 12-digit Fayda FIN number and requests verification OTP.
4. User enters the 6-digit SMS OTP received from Fayda and submits.
5. User aligns their face inside the camera frame, blinks upon instruction, and captures a live selfie.
6. User reviews read-only demographic details (Name, DOB, Gender) retrieved from Fayda.
7. User fills out bank-specific details (Address, Occupation, Source of Funds) and confirms account tier "Standard Savings".
8. User draws their digital signature on the touchscreen and taps "Submit Application".
9. System displays real-time processing indicator, transitions to confirmed status, and renders the newly issued bank account number and activation instructions.

## Required System Components (what must be running)

- `api` — API Gateway and FastAPI application server with real PostgreSQL and Redis.
- `worker` — Bank submission background consumer daemon executing `python -m src.workers.bank_submission`.
- `postgres` — Real PostgreSQL database storing applications, identity snapshots, and audit ledger.
- `redis` — Real Redis instance managing session cache and `bank_submission_queue`.
- `fayda-sandbox` — Live sandbox endpoint simulating Fayda eKYC verification and demographic payload.
- `cbs-sandbox` — Live sandbox endpoint simulating partner bank CBS account creation.

## Assertion Points (what proves this worked)

- AP-1 Database: `applications` table row has `status='ACCOUNT_OPENED'` and non-null `idempotency_hash`.
- AP-2 Database: `identity_snapshots` table row has `verification_method='OTP'` and encrypted demographics.
- AP-3 Queue: `bank_submission_queue` message was consumed and acknowledged by `bank_submission_worker`.
- AP-4 External API: `fayda_ekyc_api` sandbox received verification request and returned HTTP 200 with verified claims.
- AP-5 External API: `bank_cbs_api` sandbox received verified submission payload and returned a generated account number.
- AP-6 Audit: `audit_logs` table contains hash-chained entries for `CONSENT_GRANTED`, `IDENTITY_VERIFIED`, `LIVENESS_PASSED`, and `APPLICATION_SUBMITTED`.
- AP-7 Latency: Complete application submission to account issuance round-trip completes within 5.0 seconds.

## Failure Modes to Test

- CH-01 Client Session Token Expiry mid-journey triggers re-authentication prompt without dropping form draft state.
- CH-04 Fayda eKYC sandbox transient timeout of 5000ms triggers automated retry with exponential backoff.
- CH-06 Duplicate application submission with identical idempotency key returns existing active record with HTTP 409.
