# Journey Loop: loop_journey_07_bank-offline-retry
journey_file: journeys/journey_07_bank-offline-retry.md
covers: AS-07
priority: critical

## Objective
This journey loop proves end-to-end functionality for `journeys/journey_07_bank-offline-retry.md`.
It adds NO NEW production behavior: its sole purpose is black-box verification of what the component loops built against a real running system.

## Assertion Points to Prove
- AP-1 Customer submission successfully enters transactional outbox in PostgreSQL and transitions state to SUBMITTED_TO_BANK
- AP-2 Bank CBS simulated outage (HTTP 503) causes bank_submission_worker to record retry attempt with exponential backoff
- AP-3 Message remains pending in queue/outbox with incremented retry_count and next_attempt_at timestamp
- AP-4 Upon CBS recovery, worker delivers payload and receives generated account number
- AP-5 Application state updates to ACCOUNT_OPENED with zero duplicate account creations

## Boundaries & Environment
- Real boundaries: `db, queue, external_api, worker`
- Services running: `postgres redis cbs-sandbox worker api`
- Required credentials: `BANK_API_KEY`
