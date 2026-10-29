# Loop Instruction: Bank Core Banking System API Client & Sandbox Gateway
loop_name: loop_unit_06_bank-cbs-api
node_id: bank_cbs_api
spec_ref: §3

## Scoped Build Context
This component loop builds `bank_cbs_api` strictly scoped to `§3` of `system_guide.md`.
It must produce the declared production target paths and satisfy all unit, integration, and contract tests.

## Target Paths
- `src/clients/bank_cbs_client.py`
- `sandbox/bank_cbs_sandbox.py`

## Boundaries & Dependencies
- Boundaries: `external_api`
- Dependencies: `none`
