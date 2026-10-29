# Debugger Agent Strategy: loop_unit_09_submission-event

1. Execute `./verify.sh` to observe failing tests or gate errors.
2. If code logic is wrong, fix the implementation files in `target_paths`.
3. Fix test code ONLY if the test assertion contradicts `system_guide.md` or has a stale contract.
4. NEVER fix a test failure by mocking a declared boundary (queue).
5. Max retry: if 5 iterations pass without `verify.sh` exiting 0, stop and surface the blocker.
