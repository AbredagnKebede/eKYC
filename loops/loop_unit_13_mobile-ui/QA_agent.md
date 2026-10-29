# QA Agent Strategy: loop_unit_13_mobile-ui

## Test Plan
- Write unit tests under `tests/unit/test_mobile_ui.py` testing business logic, edge conditions, and validation invariants.
- Pure unit tests — no integration boundary required.

## Boundary Policy
Mocks are permitted in `tests/unit/` and `tests/component/` only.
For declared boundaries (`none`), integration tests MUST exercise the real boundary.
Silent mocks at declared boundaries will fail `check_mocks.py`.
