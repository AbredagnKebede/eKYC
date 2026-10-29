# QA Agent Strategy: loop_unit_05_identity-service

## Test Plan
- Write unit tests under `tests/unit/test_identity_service.py` testing business logic, edge conditions, and validation invariants.
- Write integration tests under `tests/integration/test_identity_service.py` verifying live boundary interactions against real running services (postgres fayda-sandbox).

## Boundary Policy
Mocks are permitted in `tests/unit/` and `tests/component/` only.
For declared boundaries (`db, external_api`), integration tests MUST exercise the real boundary.
Silent mocks at declared boundaries will fail `check_mocks.py`.
