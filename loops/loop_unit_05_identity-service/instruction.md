# Loop Instruction: Identity Verification & ONNX Liveness Inference Service
loop_name: loop_unit_05_identity-service
node_id: identity_service
spec_ref: §3, §6

## Scoped Build Context
This component loop builds `identity_service` strictly scoped to `§3, §6` of `system_guide.md`.
It must produce the declared production target paths and satisfy all unit, integration, and contract tests.

## Target Paths
- `src/services/identity.py`
- `src/security/encryption.py`
- `src/security/liveness.py`

## Boundaries & Dependencies
- Boundaries: `db, external_api`
- Dependencies: `loop_unit_01_db-postgres, loop_unit_04_fayda-api`
