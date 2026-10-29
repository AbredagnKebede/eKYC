# QA Agent Strategy: loop_unit_10_onboarding-service

## Test Plan
- Write unit tests under `tests/unit/test_onboarding_service.py` testing business logic, edge conditions, and validation invariants.
- Write integration tests under `tests/integration/test_onboarding_service.py` verifying live boundary interactions against real running services (postgres redis).

## Boundary Policy
Mocks are permitted in `tests/unit/` and `tests/component/` only.
For declared boundaries (`db, queue`), integration tests MUST exercise the real boundary.
Silent mocks at declared boundaries will fail `check_mocks.py`.
