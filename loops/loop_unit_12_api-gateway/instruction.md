# Loop Instruction: FastAPI REST API Gateway, Auth Middleware & Ingress
loop_name: loop_unit_12_api-gateway
node_id: api_gateway
spec_ref: §3

## Scoped Build Context
This component loop builds `api_gateway` strictly scoped to `§3` of `system_guide.md`.
It must produce the declared production target paths and satisfy all unit, integration, and contract tests.

## Target Paths
- `src/api/main.py`
- `src/api/routes/applications.py`
- `src/api/routes/banks.py`
- `src/api/middleware.py`

## Boundaries & Dependencies
- Boundaries: `db`
- Dependencies: `loop_unit_02_cache-redis, loop_unit_05_identity-service, loop_unit_10_onboarding-service`
