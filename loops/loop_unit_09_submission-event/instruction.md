# Loop Instruction: Application Submitted Event Contract & Serialization
loop_name: loop_unit_09_submission-event
node_id: application_submitted_event
spec_ref: §5

## Scoped Build Context
This component loop builds `application_submitted_event` strictly scoped to `§5` of `system_guide.md`.
It must produce the declared production target paths and satisfy all unit, integration, and contract tests.

## Target Paths
- `src/events/application_submitted.py`

## Boundaries & Dependencies
- Boundaries: `queue`
- Dependencies: `loop_unit_08_submission-queue`
