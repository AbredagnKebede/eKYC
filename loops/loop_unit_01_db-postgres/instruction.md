# Loop Instruction: PostgreSQL Primary Database Models & Schema
loop_name: loop_unit_01_db-postgres
node_id: db_postgres
spec_ref: §2

## Scoped Build Context
This component loop builds `db_postgres` strictly scoped to `§2` of `system_guide.md`.
It must produce the declared production target paths and satisfy all unit, integration, and contract tests.

## Target Paths
- `src/models/base.py`
- `src/models/application.py`
- `src/models/audit.py`
- `migrations/env.py`

## Boundaries & Dependencies
- Boundaries: `db`
- Dependencies: `none`
