# Verification Checklist: loop_unit_06_bank-cbs-api

- [ ] Implement outbound HTTP client for Core Banking System account opening with BANK_API_KEY
- [ ] Implement sandbox HTTP server simulating bank CBS account creation, idempotency, and account number generation
- [ ] Implement timeout and circuit-breaker handling for CBS outages
- [ ] Unit tests for outbound CBS payload formatting and error mapping
- [ ] Integration tests verifying live HTTP handshake and account number issuance against running cbs-sandbox
- [ ] Code coverage ≥ 85%
- [ ] Minimum 85% line coverage on target paths
- [ ] Meaningful assertions checked via check_assertions.py
- [ ] No silent mocks at critical boundaries (external_api)
