# Loop Instruction: Onboarding State Machine & Application Lifecycle Service
loop_name: loop_unit_10_onboarding-service
node_id: onboarding_service
spec_ref: §4, §5

## Scoped Build Context
This component loop builds `onboarding_service` strictly scoped to `§4, §5` of `system_guide.md`.
It must produce the declared production target paths and satisfy all unit, integration, and contract tests.

## Target Paths
- `src/services/onboarding.py`
- `src/state/machine.py`

## Boundaries & Dependencies
- Boundaries: `db, queue`
- Dependencies: `loop_unit_01_db-postgres, loop_unit_03_audit-service, loop_unit_05_identity-service, loop_unit_08_submission-queue, loop_unit_09_submission-event`
