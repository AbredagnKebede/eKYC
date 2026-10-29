# Journey Loop: loop_journey_05_liveness-spoof-rejection
journey_file: journeys/journey_05_liveness-spoof-rejection.md
covers: AS-05
priority: critical

## Objective
This journey loop proves end-to-end functionality for `journeys/journey_05_liveness-spoof-rejection.md`.
It adds NO NEW production behavior: its sole purpose is black-box verification of what the component loops built against a real running system.

## Assertion Points to Prove
- AP-1 ONNX inference engine detects static/replayed face frame and returns spoof score < 0.90
- AP-2 Rejection response returned with HTTP 422 and actionable remediation prompt
- AP-3 After 3 consecutive spoof rejections, application state transitions to LIVENESS_FAILED in database
- AP-4 Biometric image frame buffers are purged from memory with zero persistent file retention

## Boundaries & Environment
- Real boundaries: `db`
- Services running: `postgres redis api`
- Required credentials: ``
