# Journey: Idempotent Submission Handling Transient Bank Offline
journey_id: J-07
covers: AS-07
priority: critical
graph_nodes: [ui_mobile_app, api_gateway, onboarding_service, bank_adapter_service, audit_service, db_postgres, cache_redis, bank_submission_queue, bank_submission_worker, application_submitted_event, bank_cbs_api]

## User Steps (black-box perspective)

1. User completes all verification steps, signs their application, and taps "Submit Application".
2. System confirms receipt, transitions application status to `SUBMITTED_TO_BANK`, and presents the status tracking dashboard: "Application submitted. Communicating with bank...".
3. Meanwhile, the partner bank's Core Banking System (CBS) is experiencing a scheduled 10-minute maintenance downtime (returning HTTP 503 Service Unavailable).
4. App continues to display clear pending status without showing any fatal error or forcing the user to re-enter data.
5. When the partner bank CBS recovers, the system worker automatically dispatches the queued payload and transitions the application to `BANK_ACCEPTED` without user intervention.

## Required System Components (what must be running)

- `api` — API Gateway receiving the submit request.
- `worker` — `bank_submission_worker` background consumer polling and executing backoff retries.
- `postgres` — PostgreSQL holding application state and transactional outbox.
- `redis` — Redis managing `bank_submission_queue`.
- `cbs-sandbox` — Live sandbox endpoint configured initially in HTTP 503 mode, then switched to HTTP 200 mode.

## Assertion Points (what proves this worked)

- AP-1 Database: `applications` status remains reliably in `SUBMITTED_TO_BANK` during bank downtime.
- AP-2 Database: `bank_submissions` records `retry_count >= 1` and logs `last_error='HTTP 503 Service Unavailable'`.
- AP-3 Queue: The message remains safely in flight or requeued with exponential backoff delay.
- AP-4 External API: Once CBS returns HTTP 200, exactly one bank account creation payload is accepted; zero duplicate accounts are opened.
- AP-5 Audit: `audit_logs` records `SUBMISSION_RETRY_SCHEDULED` and subsequent `SUBMISSION_SUCCEEDED`.

## Failure Modes to Test

- CH-05 Consecutive failures exceeding max retry count (5 attempts) move the message to dead-letter queue (`bank_submission_dlq`) and flag for operator review.
- CH-07 Worker process crash mid-retry restarts cleanly, re-reads the pending outbox entry from PostgreSQL, and resumes dispatch.
