# Verification Checklist: loop_unit_10_onboarding-service

- [x] Implement onboarding state machine transitions: DRAFT -> CONSENTED -> ID_VERIFIED -> LIVENESS_PASSED -> DATA_COMPLETE -> SUBMITTED_TO_BANK
- [x] Implement state guard checks (active consent, verified identity, dynamic form validity, signature)
- [x] Verify onboarding_service can publish application_submitted_event upon customer signature
- [x] Implement transactional outbox pattern writing application state and outbox record in a single ACID transaction
- [x] Unit tests for all valid and invalid state machine transitions
- [x] Integration tests verifying PostgreSQL ACID state commitment and outbox queuing
- [x] Code coverage ≥ 85%
- [x] Minimum 85% line coverage on target paths
- [x] Meaningful assertions checked via check_assertions.py
- [x] No silent mocks at critical boundaries (db, queue)
