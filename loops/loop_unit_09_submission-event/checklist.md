# Verification Checklist: loop_unit_09_submission-event

- [x] Define strict Pydantic v2 event schema for application_submitted_event with payload signatures
- [x] Verify contract test for application_submitted_event publish schema specification
- [x] Verify contract test for application_submitted_event consume schema validation
- [x] Unit tests verifying strict field validation, type checking, and timestamp formatting
- [x] Integration tests publishing and consuming event payload through Redis stream
- [x] Code coverage ≥ 85%
- [x] Minimum 85% line coverage on target paths
- [x] Meaningful assertions checked via check_assertions.py
- [x] No silent mocks at critical boundaries (queue)
