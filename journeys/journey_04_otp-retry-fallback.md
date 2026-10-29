# Journey: OTP Verification Retry Exhaustion Branch Fallback
journey_id: J-04
covers: AS-04
priority: critical
graph_nodes: [ui_mobile_app, api_gateway, onboarding_service, identity_service, audit_service, db_postgres, cache_redis, fayda_ekyc_api]

## User Steps (black-box perspective)

1. User enters a valid 12-digit Fayda FIN and triggers OTP generation.
2. User enters an incorrect 6-digit OTP code on the verification screen; system reports "Invalid OTP. 2 attempts remaining."
3. User enters a second incorrect OTP code; system reports "Invalid OTP. 1 attempt remaining."
4. User enters a third incorrect OTP code.
5. System displays a verification lockout screen stating: "Identity verification failed. Please visit your chosen bank branch to complete onboarding." The app displays an application reference code and a button to view nearest branches.

## Required System Components (what must be running)

- `api` — API Gateway and Identity verification service.
- `postgres` — PostgreSQL database holding application state.
- `redis` — Redis managing active OTP challenges and attempt counters.
- `fayda-sandbox` — Live sandbox endpoint simulating Fayda eKYC verification failures.

## Assertion Points (what proves this worked)

- AP-1 Database: `applications` status transitions strictly to `ID_FAILED`.
- AP-2 Cache: Redis OTP session key is deleted upon third failure, preventing any subsequent OTP submissions.
- AP-3 API response: Fourth submission receives HTTP 409 Conflict with state `ID_FAILED`.
- AP-4 Audit: `audit_logs` records `OTP_VERIFICATION_FAILED` and `APPLICATION_ID_FAILED` with consecutive failure count 3.
- AP-5 External API: `fayda_ekyc_api` sandbox registered 3 failed verification invocations.

## Failure Modes to Test

- CH-02 OTP challenge expiring at 180 seconds before 3 attempts returns HTTP 410 Gone requiring new challenge generation.
- CH-01 Interrupted mobile network connection between attempts preserves remaining attempt count correctly in Redis.
