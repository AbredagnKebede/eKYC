# Architecture and Build Patterns

## 1. Tooling and Test Execution
- **Test Runner**: `pytest`
- **Coverage Tool**: `pytest-cov`
- **Minimum Coverage Threshold**: 85% for unit and component test suites.
- **Database Migration Tool**: `alembic`
- **Migration Command**: `alembic upgrade head`
- **Local Runtime Orchestration**: `docker compose up -d postgres redis minio`

## 2. Test Suite Layout & Boundaries
All test files must strictly respect directory categorizations:

```
tests/unit/         pure functions, no I/O                    — mocks fine
tests/component/    one service, dependencies mocked          — mocks fine
tests/integration/  real DB/cache/broker, no external APIs    — no mocks at that boundary
tests/contract/     event schema + producer/consumer compat
tests/journey/      black box, real everything (journey loops only)
tests/chaos/        timeouts, retries, expiry, restart (loop_chaos only)
```

### Boundary & Mock Invariants:
1. **Critical Boundaries**: Database (`PostgreSQL`), Cache/Rate-Limiter (`Redis`), and Message Broker/Queue (`bank_submission_queue`).
2. **Journey Loops**: Black-box execution only. Tests in `tests/journey/` run against live FastAPI server instances, real PostgreSQL, real Redis, and real worker processes. Mocks are forbidden. External APIs (`fayda_ekyc_api`, `bank_cbs_api`) must point to live sandbox endpoints.
3. **Chaos Loops**: Validate resilience in `tests/chaos/` by injecting real network latency, dropping DB connections, and simulating expired tokens.

## 3. Layered Service Architecture
- **API Boundary (`src/api/`)**: FastAPI routers, request parsing, response serialization, authentication middlewares, rate-limiting dependencies.
- **Service Layer (`src/services/`)**: Business logic orchestrating state transitions (`OnboardingService`), cryptographic identity handling (`IdentityService`), and bank adapters (`BankAdapterService`).
- **Data Access & Outbox (`src/db/`)**: SQLAlchemy models, repositories, and transactional outbox table (`bank_submission_outbox`).
- **Workers (`src/workers/`)**: Background queue consumer daemon (`bank_submission_worker`) that polls or pops from `bank_submission_queue`, executes adapter dispatch, and updates application state with exponential backoff.
