# Verification Checklist: loop_unit_06_bank-cbs-api

- [x] Implement outbound HTTP client for Core Banking System account opening with BANK_API_KEY
- [x] Implement sandbox HTTP server simulating bank CBS account creation, idempotency, and account number generation
- [x] Implement timeout and circuit-breaker handling for CBS outages
- [x] Unit tests for outbound CBS payload formatting and error mapping
- [x] Integration tests verifying live HTTP handshake and account number issuance against running cbs-sandbox
- [x] Code coverage ≥ 85%
- [x] Minimum 85% line coverage on target paths
- [x] Meaningful assertions checked via check_assertions.py
- [x] No silent mocks at critical boundaries (external_api)
