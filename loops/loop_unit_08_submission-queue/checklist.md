# Verification Checklist: loop_unit_08_submission-queue

- [ ] Implement persistent queue transport using Redis Streams / consumer groups for bank_submission_queue
- [ ] Implement reliable message acknowledgement (ACK) and dead-letter queue (DLQ) re-routing
- [ ] Implement enqueue and dequeue primitives with message envelope metadata and idempotency keys
- [ ] Unit tests for queue envelope serialization and DLQ routing logic
- [ ] Integration tests with real Redis testing publish and consume message lifecycle under simulated failures
- [ ] Code coverage ≥ 85%
- [ ] Minimum 85% line coverage on target paths
- [ ] Meaningful assertions checked via check_assertions.py
- [ ] No silent mocks at critical boundaries (queue)
