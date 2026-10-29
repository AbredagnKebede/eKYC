# Journey Loop: loop_journey_04_otp-retry-fallback
journey_file: journeys/journey_04_otp-retry-fallback.md
covers: AS-04
priority: critical

## Objective
This journey loop proves end-to-end functionality for `journeys/journey_04_otp-retry-fallback.md`.
It adds NO NEW production behavior: its sole purpose is black-box verification of what the component loops built against a real running system.

## Assertion Points to Prove
- AP-1 OTP challenge generated and stored in Redis with 180s TTL and failure counter
- AP-2 Invalid OTP submissions 1 and 2 return HTTP 400 with remaining attempts counter
- AP-3 Third invalid OTP submission transitions application state to ID_FAILED in PostgreSQL
- AP-4 Further OTP verification requests for this application return HTTP 403 Forbidden
- AP-5 API returns structured response containing physical branch referral code and partner bank branch locator URL

## Boundaries & Environment
- Real boundaries: `db, external_api`
- Services running: `postgres redis fayda-sandbox api`
- Required credentials: `FAYDA_API_KEY`
