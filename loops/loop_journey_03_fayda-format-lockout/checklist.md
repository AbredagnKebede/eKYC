# Journey Checklist: loop_journey_03_fayda-format-lockout

- [ ] AP-1 Client-side form blocks submission for non-12-digit input strings with validation error
- [ ] AP-2 API endpoint /v1/applications/{id}/identity/start returns HTTP 422 for malformed identifier payloads
- [ ] AP-3 Sliding-window rate-limiting counter in Redis increments on each failed submission attempt
- [ ] AP-4 After 5 consecutive malformed submissions from same device fingerprint, endpoint responds with HTTP 429
- [ ] AP-5 Audit log records RATE_LIMIT_LOCKOUT with IP address and device identifier
- [ ] 100% of assertion points verified by black-box tests in tests/journey/j03
- [ ] Zero mocks at critical boundaries (db)
- [ ] Real processes and sandbox services running
