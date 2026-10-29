# Verification Checklist: loop_unit_11_submission-worker

- [ ] Implement daemon process entrypoint runnable via 'python -m src.workers.bank_submission'
- [ ] Verify bank_submission_worker can consume application_submitted_event from the queue
- [ ] Implement idempotent CBS dispatch with exponential retry backoff and DLQ fallback
- [ ] Implement worker heartbeat reporting to Redis key 'worker:heartbeat' every 10 seconds
- [ ] Unit tests for backoff calculation, retry limiters, and payload reconstruction
- [ ] Integration tests executing real worker process consuming queue and invoking cbs-sandbox
- [ ] Code coverage ≥ 85%
- [ ] Minimum 85% line coverage on target paths
- [ ] Meaningful assertions checked via check_assertions.py
- [ ] No silent mocks at critical boundaries (db, queue, external_api, worker)
