# Journey: Invalid Fayda National ID Format Lockout
journey_id: J-03
covers: AS-03
priority: high
graph_nodes: [ui_mobile_app, api_gateway, onboarding_service, identity_service, audit_service, db_postgres, cache_redis]

## User Steps (black-box perspective)

1. User successfully completes the consent screen and navigates to the Fayda ID entry screen.
2. User enters an invalid ID number (e.g., fewer than 12 digits or containing alphabetic characters).
3. Client immediately highlights the input field with an inline validation error and disables the "Request OTP" button.
4. User bypasses client validation or repeatedly submits malformed ID requests (5 consecutive attempts).
5. App displays a rate-limit lockout notification stating that identity requests are temporarily locked for 15 minutes due to repeated invalid attempts.

## Required System Components (what must be running)

- `api` — API Gateway enforcing input schema constraints and Redis rate-limiting dependencies.
- `postgres` — PostgreSQL database with active application record.
- `redis` — Redis cache tracking IP and device sliding-window failure attempts.

## Assertion Points (what proves this worked)

- AP-1 API response: Malformed ID payload receives HTTP 422 Unprocessable Entity with clear validation details.
- AP-2 Cache: Redis key `ratelimit:fayda:attempts:<device_id>` increments on each invalid submission.
- AP-3 API response: Sixth submission returns HTTP 429 Too Many Requests with `Retry-After: 900`.
- AP-4 Database: `applications` status remains `CONSENTED`; no unverified Fayda transaction is persisted.
- AP-5 External API: Zero requests are dispatched to external `fayda_ekyc_api`.

## Failure Modes to Test

- CH-02 Brute-force submission attempts across multiple rapid concurrent threads are atomically throttled by Redis script without race condition leakage.
