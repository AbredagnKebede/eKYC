# Verification Checklist: loop_unit_09_submission-event

- [ ] Define strict Pydantic v2 event schema for application_submitted_event with payload signatures
- [ ] Verify contract test for application_submitted_event publish schema specification
- [ ] Verify contract test for application_submitted_event consume schema validation
- [ ] Unit tests verifying strict field validation, type checking, and timestamp formatting
- [ ] Integration tests publishing and consuming event payload through Redis stream
- [ ] Code coverage ≥ 85%
- [ ] Minimum 85% line coverage on target paths
- [ ] Meaningful assertions checked via check_assertions.py
- [ ] No silent mocks at critical boundaries (queue)
