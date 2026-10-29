# Verification Checklist: loop_unit_12_api-gateway

- [ ] Implement FastAPI application routing for /v1/banks, /v1/applications/*, and /v1/webhooks/*
- [ ] Implement JWT bearer authentication and client device fingerprint binding middleware
- [ ] Implement sliding-window rate limiting middleware backed by Redis
- [ ] Implement asynchronous bank webhook callback handler with HMAC signature verification
- [ ] Unit tests for route parameter parsing, JWT validation, and HTTP error mapping
- [ ] Integration tests exercising live HTTP requests against running FastAPI test client with Postgres and Redis
- [ ] Code coverage ≥ 85%
- [ ] Minimum 85% line coverage on target paths
- [ ] Meaningful assertions checked via check_assertions.py
- [ ] No silent mocks at critical boundaries (db)
