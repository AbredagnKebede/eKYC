# Loop Instruction: Redis Session Cache & Sliding-Window Rate Limiter
loop_name: loop_unit_02_cache-redis
node_id: cache_redis
spec_ref: §2, §6

## Scoped Build Context
This component loop builds `cache_redis` strictly scoped to `§2, §6` of `system_guide.md`.
It must produce the declared production target paths and satisfy all unit, integration, and contract tests.

## Target Paths
- `src/infrastructure/redis.py`
- `src/infrastructure/rate_limiter.py`
- `src/infrastructure/session.py`

## Boundaries & Dependencies
- Boundaries: `db`
- Dependencies: `none`
