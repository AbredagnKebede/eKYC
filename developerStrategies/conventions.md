# Engineering Conventions

## 1. Code Style and Formatting
- **Python**: Enforce Python 3.11+ type hints across all function parameters and return types. Use `ruff` for linting and formatting. Line length limit is 100 characters.
- **Pydantic**: Use Pydantic v2 `BaseModel` with strict mode enabled where appropriate. Use `Field(..., description=...)` on all public API schema attributes.
- **Async First**: All I/O operations (PostgreSQL database queries, Redis cache lookups, external HTTP requests via `httpx.AsyncClient`) must be asynchronous (`async def`).

## 2. Naming Standards
- **File Names**: `snake_case.py` (e.g. `onboarding_service.py`, `bank_adapter.py`).
- **Classes**: `PascalCase` (e.g. `ApplicationStateMachine`, `AwashBankAdapter`).
- **Database Tables**: `snake_case` plural (e.g. `applications`, `identity_snapshots`, `audit_logs`).
- **API Endpoints**: Kebab-case or lower-case plural nouns with version prefix (e.g. `/v1/applications/{id}/consent`).
- **State Machine Constants**: Upper snake_case enums (e.g. `ApplicationStatus.CONSENTED`, `ApplicationStatus.ACCOUNT_OPENED`).

## 3. Git Commit Standards
- Strictly local atomic commits per completed loop. Never push automatically.
- Format: `<type>(<scope>): <summary>`
  - `feat(onboarding): implement dynamic bank form ingestion`
  - `fix(identity): enforce sliding rate limit on OTP verification`
  - `test(journey): add black-box e2e account opening assertion points`
  - `chore(deps): bump onnx runtime dependencies`

## 4. Error Handling & Exception Hierarchy
- Use RFC 7807 Problem Details for all API HTTP error payloads:
  ```json
  {
    "type": "https://errors.ekyc.et/INVALID_STATE_TRANSITION",
    "title": "Invalid State Transition",
    "status": 409,
    "detail": "Application app_123 is in state DRAFT; must be CONSENTED before verification.",
    "instance": "/v1/applications/app_123/identity/start"
  }
  ```
- Domain exceptions inherit from `DomainError` and map cleanly to HTTP status codes at the API gateway layer.
- Never swallow exceptions silently. Log with structured contextual fields (`application_id`, `bank_id`, `actor`).
