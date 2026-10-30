# Verification Checklist: loop_unit_08_submission-queue

- [x] Implement persistent queue transport using Redis Streams / consumer groups for bank_submission_queue
- [x] Implement reliable message acknowledgement (ACK) and dead-letter queue (DLQ) re-routing
- [x] Implement enqueue and dequeue primitives with message envelope metadata and idempotency keys
- [x] Unit tests for queue envelope serialization and DLQ routing logic
- [x] Integration tests with real Redis testing publish and consume message lifecycle under simulated failures
- [x] Code coverage ≥ 85%
- [x] Minimum 85% line coverage on target paths
- [x] Meaningful assertions checked via check_assertions.py
- [x] No silent mocks at critical boundaries (queue)
