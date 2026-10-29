# QA Agent Strategy: loop_unit_11_submission-worker

## Test Plan
- Write unit tests under `tests/unit/test_submission_worker.py` testing business logic, edge conditions, and validation invariants.
- Write integration tests under `tests/integration/test_submission_worker.py` verifying live boundary interactions against real running services (postgres redis cbs-sandbox).

## Boundary Policy
Mocks are permitted in `tests/unit/` and `tests/component/` only.
For declared boundaries (`db, queue, external_api, worker`), integration tests MUST exercise the real boundary.
Silent mocks at declared boundaries will fail `check_mocks.py`.
