# Journey: Asynchronous Bank Callback and Account Number Issuance
journey_id: J-08
covers: AS-08
priority: high
graph_nodes: [ui_mobile_app, api_gateway, onboarding_service, audit_service, db_postgres, cache_redis]

## User Steps (black-box perspective)

1. User submits an application for an account tier requiring manual bank AML compliance officer review.
2. App status tracker indicates: "Application received by bank. Awaiting final verification."
3. Two hours later, the partner bank completes manual review, creates the account in CBS, and fires an automated signed webhook callback to the platform.
4. User receives an in-app push notification: "Congratulations! Your Awash Bank account is open."
5. User opens the application and views their verified bank account number, branch routing code, and activation instructions.

## Required System Components (what must be running)

- `api` — API Gateway exposing `POST /v1/webhooks/bank/{bank_id}` with HMAC signature verification.
- `postgres` — PostgreSQL holding application state and audit ledger.
- `redis` — Redis managing session state and real-time status publication.

## Assertion Points (what proves this worked)

- AP-1 API response: Webhook call with valid bank HMAC signature returns HTTP 200 `{ "status": "acknowledged" }`.
- AP-2 Database: `applications` transitions atomically from `BANK_ACCEPTED` to `status='ACCOUNT_OPENED'`.
- AP-3 Database: `bank_submissions` records issued `account_number` and sets `bank_status='opened'`.
- AP-4 Security: Webhook call with tampered or invalid HMAC signature is rejected with HTTP 401 Unauthorized.
- AP-5 Audit: `audit_logs` records `BANK_STATUS_WEBHOOK_PROCESSED` with bank reference and verified payload hash.

## Failure Modes to Test

- CH-06 Duplicate webhook callbacks with identical account number return HTTP 200 idempotent acknowledgment without duplicate status mutation.
- CH-08 Out-of-order webhook delivery (e.g. `ACCOUNT_OPENED` before `BANK_ACCEPTED` finishes processing) is reconciled safely by state machine transition guards.
