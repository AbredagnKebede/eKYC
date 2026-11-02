# Journey Checklist: loop_journey_07_bank-offline-retry

- [x] AP-1 Customer submission successfully enters transactional outbox in PostgreSQL and transitions state to SUBMITTED_TO_BANK
- [x] AP-2 Bank CBS simulated outage (HTTP 503) causes bank_submission_worker to record retry attempt with exponential backoff
- [x] AP-3 Message remains pending in queue/outbox with incremented retry_count and next_attempt_at timestamp
- [x] AP-4 Upon CBS recovery, worker delivers payload and receives generated account number
- [x] AP-5 Application state updates to ACCOUNT_OPENED with zero duplicate account creations
- [x] 100% of assertion points verified by black-box tests in tests/journey/j07
- [x] Zero mocks at critical boundaries (db, queue, external_api, worker)
- [x] Real processes and sandbox services running
