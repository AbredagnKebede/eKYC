# Loop Instruction: Bank Submission Background Worker Daemon
loop_name: loop_unit_11_submission-worker
node_id: bank_submission_worker
spec_ref: §5

## Scoped Build Context
This component loop builds `bank_submission_worker` strictly scoped to `§5` of `system_guide.md`.
It must produce the declared production target paths and satisfy all unit, integration, and contract tests.

## Target Paths
- `src/workers/bank_submission.py`

## Boundaries & Dependencies
- Boundaries: `db, queue, external_api, worker`
- Dependencies: `loop_unit_01_db-postgres, loop_unit_03_audit-service, loop_unit_07_bank-adapter-service, loop_unit_08_submission-queue, loop_unit_09_submission-event`
