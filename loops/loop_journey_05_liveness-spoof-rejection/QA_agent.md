# QA Agent Strategy: loop_journey_05_liveness-spoof-rejection

## Scope
Write black-box journey tests strictly in `tests/journey/j05`.
Every test must cite its corresponding `AP-<n>` identifier in docstring/test name.
At least one test must carry the `black_box` marker.

## Critical Invariant: No Silent Mocks
This journey loop exercises live processes:
- Real PostgreSQL database (not SQLite or in-memory)
- Real Redis instance
- Real worker daemon running in its own process
- Real sandbox endpoints (postgres redis api)
Any use of `unittest.mock`, `jest.mock`, `responses`, fakes, or in-memory DBs will fail the gate.
