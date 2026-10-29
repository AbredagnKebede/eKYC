# Loop Instruction: Fayda eKYC API Client & Sandbox Gateway
loop_name: loop_unit_04_fayda-api
node_id: fayda_ekyc_api
spec_ref: §3

## Scoped Build Context
This component loop builds `fayda_ekyc_api` strictly scoped to `§3` of `system_guide.md`.
It must produce the declared production target paths and satisfy all unit, integration, and contract tests.

## Target Paths
- `src/clients/fayda_client.py`
- `sandbox/fayda_sandbox.py`

## Boundaries & Dependencies
- Boundaries: `external_api`
- Dependencies: `none`
