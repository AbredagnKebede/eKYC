# Journey Checklist: loop_journey_04_otp-retry-fallback

- [ ] AP-1 OTP challenge generated and stored in Redis with 180s TTL and failure counter
- [ ] AP-2 Invalid OTP submissions 1 and 2 return HTTP 400 with remaining attempts counter
- [ ] AP-3 Third invalid OTP submission transitions application state to ID_FAILED in PostgreSQL
- [ ] AP-4 Further OTP verification requests for this application return HTTP 403 Forbidden
- [ ] AP-5 API returns structured response containing physical branch referral code and partner bank branch locator URL
- [ ] 100% of assertion points verified by black-box tests in tests/journey/j04
- [ ] Zero mocks at critical boundaries (db, external_api)
- [ ] Real processes and sandbox services running
