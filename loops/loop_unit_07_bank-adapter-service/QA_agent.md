# QA Agent Strategy: loop_unit_07_bank-adapter-service

## Test Plan
- Write unit tests under `tests/unit/test_bank_adapter.py` testing business logic, edge conditions, and validation invariants.
- Write integration tests under `tests/integration/test_bank_adapter.py` verifying live boundary interactions against real running services (cbs-sandbox).

## Boundary Policy
Mocks are permitted in `tests/unit/` and `tests/component/` only.
For declared boundaries (`external_api`), integration tests MUST exercise the real boundary.
Silent mocks at declared boundaries will fail `check_mocks.py`.
