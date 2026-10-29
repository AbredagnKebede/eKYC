# Verification Checklist: loop_unit_04_fayda-api

- [ ] Implement HTTP client for Fayda VeriFayda 2 OIDC verification endpoint with FAYDA_API_KEY
- [ ] Implement sandbox HTTP server simulating citizen OTP generation, verification, and demographic assertions
- [ ] Implement exponential backoff retry policy for transient 5000ms timeouts
- [ ] Unit tests for request payload formatting and response signature parsing
- [ ] Integration tests verifying live HTTP handshake against running fayda-sandbox
- [ ] Code coverage ≥ 85%
- [ ] Minimum 85% line coverage on target paths
- [ ] Meaningful assertions checked via check_assertions.py
- [ ] No silent mocks at critical boundaries (external_api)
