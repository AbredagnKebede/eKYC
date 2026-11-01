# Verification Checklist: loop_unit_11_submission-worker

- [x] Implement daemon process entrypoint runnable via 'python -m src.workers.bank_submission'
- [x] Verify bank_submission_worker can consume application_submitted_event from the queue
- [x] Implement idempotent CBS dispatch with exponential retry backoff and DLQ fallback
- [x] Implement worker heartbeat reporting to Redis key 'worker:heartbeat' every 10 seconds
- [x] Unit tests for backoff calculation, retry limiters, and payload reconstruction
- [x] Integration tests executing real worker process consuming queue and invoking cbs-sandbox
- [x] Code coverage ≥ 85%
- [x] Minimum 85% line coverage on target paths
- [x] Meaningful assertions checked via check_assertions.py
- [x] No silent mocks at critical boundaries (db, queue, external_api, worker)
