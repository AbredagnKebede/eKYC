# Verification Checklist: loop_unit_04_fayda-api

- [x] Implement HTTP client for Fayda VeriFayda 2 OIDC verification endpoint with FAYDA_API_KEY
- [x] Implement sandbox HTTP server simulating citizen OTP generation, verification, and demographic assertions
- [x] Implement exponential backoff retry policy for transient 5000ms timeouts
- [x] Unit tests for request payload formatting and response signature parsing
- [x] Integration tests verifying live HTTP handshake against running fayda-sandbox
- [x] Code coverage ≥ 85%
- [x] Minimum 85% line coverage on target paths
- [x] Meaningful assertions checked via check_assertions.py
- [x] No silent mocks at critical boundaries (external_api)
