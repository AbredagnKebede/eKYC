# Journey Loop: loop_journey_08_async-bank-callback
journey_file: journeys/journey_08_async-bank-callback.md
covers: AS-08
priority: high

## Objective
This journey loop proves end-to-end functionality for `journeys/journey_08_async-bank-callback.md`.
It adds NO NEW production behavior: its sole purpose is black-box verification of what the component loops built against a real running system.

## Assertion Points to Prove
- AP-1 Bank webhook callback endpoint validates HMAC signature header against registered bank secret key
- AP-2 Valid callback payload updates application status to ACCOUNT_OPENED and stores issued account_number
- AP-3 Audit trail records BANK_CALLBACK_PROCESSED with bank reference identifier
- AP-4 Polling GET /v1/applications/{id} reflects ACCOUNT_OPENED status with account number and activation instructions
- AP-5 Invalid HMAC signature on webhook triggers immediate HTTP 401 and rejects state update

## Boundaries & Environment
- Real boundaries: `db`
- Services running: `postgres redis api`
- Required credentials: ``
