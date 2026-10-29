# QA Agent Strategy: loop_chaos

## Scope
Write resilience tests in `tests/chaos`.
Every test must cite its corresponding `CH-<n>` identifier.
Fault injection (e.g. injecting network delay, killing worker processes, sending concurrent duplicate HTTP requests) is expected.
Faking or mocking the boundaries being injected into is NOT allowed.
