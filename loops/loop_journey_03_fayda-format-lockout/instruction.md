# Journey Loop: loop_journey_03_fayda-format-lockout
journey_file: journeys/journey_03_fayda-format-lockout.md
covers: AS-03
priority: high

## Objective
This journey loop proves end-to-end functionality for `journeys/journey_03_fayda-format-lockout.md`.
It adds NO NEW production behavior: its sole purpose is black-box verification of what the component loops built against a real running system.

## Assertion Points to Prove
- AP-1 Client-side form blocks submission for non-12-digit input strings with validation error
- AP-2 API endpoint /v1/applications/{id}/identity/start returns HTTP 422 for malformed identifier payloads
- AP-3 Sliding-window rate-limiting counter in Redis increments on each failed submission attempt
- AP-4 After 5 consecutive malformed submissions from same device fingerprint, endpoint responds with HTTP 429
- AP-5 Audit log records RATE_LIMIT_LOCKOUT with IP address and device identifier

## Boundaries & Environment
- Real boundaries: `db`
- Services running: `postgres redis api`
- Required credentials: ``
