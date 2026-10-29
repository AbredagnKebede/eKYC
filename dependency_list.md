# External Dependency & Blocker List

## 1. External Human Blockers & Governance

| ID | Dependency / Blocker | Impact | Mitigation / Working Assumption |
|---|---|---|---|
| **DEP-001** | Official Fayda / NIDP Relying Party Agreement & EthSwitch VeriFayda 2 direct access | Defines whether platform calls VeriFayda directly or through partner bank gateway | Design `IdentityService` and `BankAdapter` with a dual-mode connector: capable of direct VeriFayda invocation or formatting payloads for bank-routed calls. Sandbox simulation implemented for verified loops. |
| **DEP-002** | National Bank of Ethiopia (NBE) regulatory limits on remote eKYC account tiers | Sets initial transaction/balance limits for accounts opened without physical branch visit | Support dynamic `tier` configurations per bank adapter (`basic`, `standard`) with explicit transaction caps passed down from bank schemas. |
| **DEP-003** | Individual Bank Core Banking System (CBS) sandbox endpoints and authentication specs | Affects specific bank payload formatting (e.g. SOAP/XML for Finacle vs REST/JSON for modern CBS) | Implement standardized `BankAdapter` abstract interface with pluggable serializer/transport strategies. |
| **DEP-004** | In-country cloud hosting infrastructure availability (Ethio Telecom / Raxio / Wingu) | Data localization compliance for database and audit logs | Design architecture to be fully containerized (Docker / Docker Compose / Kubernetes) so it can deploy to any local on-premise or sovereign data center. |

## 2. External API Credentials & Sandbox Endpoints

| Node ID | Credential Env Variable | Sandbox Env Variable | Default Sandbox Base URL | Purpose |
|---|---|---|---|---|
| `fayda_ekyc_api` | `FAYDA_API_KEY` | `FAYDA_SANDBOX_URL` | `http://127.0.0.1:8081/fayda/v2` | Verifies citizen national ID and provides official photo/demographics |
| `bank_cbs_api` | `BANK_API_KEY` | `BANK_CBS_SANDBOX_URL` | `http://127.0.0.1:8082/cbs/v1` | Bank Core Banking System API for receiving applications and issuing account numbers |

## 3. Platform Configuration & Infrastructure Variables

| Variable Name | Default Value / Target | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ekyc_db` | PostgreSQL connection string |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis instance for session state, OTP limits, and queues |
| `JWT_SECRET_KEY` | `dev-insecure-jwt-secret-replace-in-prod` | Signing key for short-lived client session tokens |
| `HMAC_SALT_KEY` | `dev-insecure-hmac-salt-replace-in-prod` | Salt key for hashing Fayda FIN/FAN identifiers |
| `AES_MASTER_KEY` | `01234567890123456789012345678901` | 256-bit encryption key for demographic PII snapshots |
