# QA Agent Strategy: loop_unit_08_submission-queue

## Test Plan
- Write unit tests under `tests/unit/test_submission_queue.py` testing business logic, edge conditions, and validation invariants.
- Write integration tests under `tests/integration/test_submission_queue.py` verifying live boundary interactions against real running services (redis).

## Boundary Policy
Mocks are permitted in `tests/unit/` and `tests/component/` only.
For declared boundaries (`queue`), integration tests MUST exercise the real boundary.
Silent mocks at declared boundaries will fail `check_mocks.py`.
