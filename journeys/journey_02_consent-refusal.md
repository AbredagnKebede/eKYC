# Journey: User Refuses Consent Halts Flow
journey_id: J-02
covers: AS-02
priority: high
graph_nodes: [ui_mobile_app, api_gateway, onboarding_service, audit_service, db_postgres, cache_redis]

## User Steps (black-box perspective)

1. User selects "Dashen Bank" from the bank discovery catalog.
2. User views the mandatory consent agreement screen displaying required data permissions.
3. User taps "Decline and Exit".
4. App presents a confirmation dialog explaining that identity verification cannot proceed without consent; user confirms cancellation.
5. System safely terminates the onboarding session, returns the user to the landing screen, and verifies that no identity verification calls were made.

## Required System Components (what must be running)

- `api` — API Gateway and FastAPI application server.
- `postgres` — Real PostgreSQL database storing application lifecycle state.
- `redis` — Real Redis instance managing session tokens.

## Assertion Points (what proves this worked)

- AP-1 Database: `applications` record transitions directly to `status='CANCELLED'`.
- AP-2 Database: `identity_snapshots` has 0 rows for this application ID.
- AP-3 Audit: `audit_logs` records a single `CONSENT_REFUSED` event with actor and device metadata.
- AP-4 API response: `POST /v1/applications/{id}/identity/start` returns HTTP 403 Forbidden with `CONSENT_REQUIRED`.

## Failure Modes to Test

- CH-01 Expired session token during consent review rejects further actions with HTTP 401.
- CH-06 Concurrent duplicate cancellation requests resolve deterministically to `CANCELLED` without database lock collision.
