# Chaos Verification Checklist

- [ ] CH-01: Client Session Token Expiry mid-journey triggers re-authentication prompt without dropping draft state
- [ ] CH-02: Fayda eKYC OTP Challenge Expiry (180s) invalidates session and returns HTTP 410 Gone
- [ ] CH-03: Incomplete Application Draft Expiration after 24 hours triggers status EXPIRED and cryptographic shredding
- [ ] CH-04: Fayda eKYC External Call Timeout (5000ms) triggers exponential backoff retry and circuit breaker
- [ ] CH-05: Bank CBS Outbound Adapter Submission Timeout (8000ms) with per-bank circuit breaker isolation
- [ ] CH-06: Duplicate Submission Race Condition handled atomically via row-level locks and 30-day idempotency hash
- [ ] CH-07: Crash Between Database Transition and Message Enqueue handled safely by Transactional Outbox pattern
- [ ] CH-08: Bank CBS Permanent Rejection & Dead-Letter Escalation moves payload to bank_submission_dlq
- [ ] Every CH-<n> scenario cited by at least one test in tests/chaos
- [ ] No silent mocks at boundaries (db, queue, external_api, worker)
- [ ] Real processes and sandbox services running during fault injection
