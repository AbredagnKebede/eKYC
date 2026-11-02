# Chaos Verification Checklist

- [x] CH-01: Client Session Token Expiry mid-journey triggers re-authentication prompt without dropping draft state
- [x] CH-02: Fayda eKYC OTP Challenge Expiry (180s) invalidates session and returns HTTP 410 Gone
- [x] CH-03: Incomplete Application Draft Expiration after 24 hours triggers status EXPIRED and cryptographic shredding
- [x] CH-04: Fayda eKYC External Call Timeout (5000ms) triggers exponential backoff retry and circuit breaker
- [x] CH-05: Bank CBS Outbound Adapter Submission Timeout (8000ms) with per-bank circuit breaker isolation
- [x] CH-06: Duplicate Submission Race Condition handled atomically via row-level locks and 30-day idempotency hash
- [x] CH-07: Crash Between Database Transition and Message Enqueue handled safely by Transactional Outbox pattern
- [x] CH-08: Bank CBS Permanent Rejection & Dead-Letter Escalation moves payload to bank_submission_dlq
- [x] Every CH-<n> scenario cited by at least one test in tests/chaos
- [x] No silent mocks at boundaries (db, queue, external_api, worker)
- [x] Real processes and sandbox services running during fault injection
