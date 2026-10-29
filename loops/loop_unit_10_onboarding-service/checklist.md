# Verification Checklist: loop_unit_10_onboarding-service

- [ ] Implement onboarding state machine transitions: DRAFT -> CONSENTED -> ID_VERIFIED -> LIVENESS_PASSED -> DATA_COMPLETE -> SUBMITTED_TO_BANK
- [ ] Implement state guard checks (active consent, verified identity, dynamic form validity, signature)
- [ ] Verify onboarding_service can publish application_submitted_event upon customer signature
- [ ] Implement transactional outbox pattern writing application state and outbox record in a single ACID transaction
- [ ] Unit tests for all valid and invalid state machine transitions
- [ ] Integration tests verifying PostgreSQL ACID state commitment and outbox queuing
- [ ] Code coverage ≥ 85%
- [ ] Minimum 85% line coverage on target paths
- [ ] Meaningful assertions checked via check_assertions.py
- [ ] No silent mocks at critical boundaries (db, queue)
