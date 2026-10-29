# Loop Instruction: Cryptographic Audit Ledger Service
loop_name: loop_unit_03_audit-service
node_id: audit_service
spec_ref: §6

## Scoped Build Context
This component loop builds `audit_service` strictly scoped to `§6` of `system_guide.md`.
It must produce the declared production target paths and satisfy all unit, integration, and contract tests.

## Target Paths
- `src/services/audit.py`
- `src/security/hash_chain.py`

## Boundaries & Dependencies
- Boundaries: `db`
- Dependencies: `loop_unit_01_db-postgres`
