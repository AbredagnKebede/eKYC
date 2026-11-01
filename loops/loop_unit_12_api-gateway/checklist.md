# Verification Checklist: loop_unit_12_api-gateway

- [x] Implement FastAPI application routing for /v1/banks, /v1/applications/*, and /v1/webhooks/*
- [x] Implement JWT bearer authentication and client device fingerprint binding middleware
- [x] Implement sliding-window rate limiting middleware backed by Redis
- [x] Implement asynchronous bank webhook callback handler with HMAC signature verification
- [x] Unit tests for route parameter parsing, JWT validation, and HTTP error mapping
- [x] Integration tests exercising live HTTP requests against running FastAPI test client with Postgres and Redis
- [x] Code coverage ≥ 85%
- [x] Minimum 85% line coverage on target paths
- [x] Meaningful assertions checked via check_assertions.py
- [x] No silent mocks at critical boundaries (db)
