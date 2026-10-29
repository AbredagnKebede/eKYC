# Loop Instruction: Bank Adapter Service & Awash Finacle Connector
loop_name: loop_unit_07_bank-adapter-service
node_id: bank_adapter_service
spec_ref: §3

## Scoped Build Context
This component loop builds `bank_adapter_service` strictly scoped to `§3` of `system_guide.md`.
It must produce the declared production target paths and satisfy all unit, integration, and contract tests.

## Target Paths
- `src/services/bank_adapter.py`
- `src/adapters/awash_finacle.py`

## Boundaries & Dependencies
- Boundaries: `external_api`
- Dependencies: `loop_unit_06_bank-cbs-api`
