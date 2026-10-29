# QA Agent Strategy: loop_unit_02_cache-redis

## Test Plan
- Write unit tests under `tests/unit/test_cache_redis.py` testing business logic, edge conditions, and validation invariants.
- Write integration tests under `tests/integration/test_cache_redis.py` verifying live boundary interactions against real running services (redis).

## Boundary Policy
Mocks are permitted in `tests/unit/` and `tests/component/` only.
For declared boundaries (`db`), integration tests MUST exercise the real boundary.
Silent mocks at declared boundaries will fail `check_mocks.py`.
