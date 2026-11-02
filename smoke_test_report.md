# Deployment Validation & Smoke Test Report

**Release Date:** 2026-11-03  
**Target Environment:** Local Docker Compose Container Cluster (`http://127.0.0.1:8005`)  
**Pipeline Stage:** Stage 6 (`deploy_validator`)  
**Gate Status:** PASSED (`check_release_evidence.py` verified 8/8 artifacts, exit 0)

---

## 1. Container Images & Build Artifacts

Every image was built from pristine Dockerfiles and verified with reproducible SHA-256 digests:

| Image Name | Tag | Dockerfile | SHA-256 Image Digest |
|---|---|---|---|
| **`ekyc-api`** | `latest` | `Dockerfile.api` | `sha256:d9ed3eb27afd6bd9c9d1b168972ac5b03d22c099552404cab533402a99aea4a8` |
| **`ekyc-worker`** | `latest` | `Dockerfile.worker` | `sha256:66518fc6447a3139bbdf29c929f8a682f6bcfd297b2d6c3f2d14aa388c1050c1` |
| **`postgres`** | `16-alpine` | Base Image | `sha256:108b27c919e6e7bc124350fb265deea9adac58e118eade428c6d1ad44b90debe` |
| **`redis`** | `7-alpine` | Base Image | `sha256:9210b8dc25f122eb00e5572dcc7147c8e11fb1a08308b088e06c9d5dd2aa49d6` |
| **`fayda-sandbox`** | `python:3.12-slim` | Base Image | `sha256:25c5b8011a3425a140bf5fa73be0feabd3c0d5b323eecb19dc02437a368ae075` |
| **`cbs-sandbox`** | `python:3.12-slim` | Base Image | `sha256:25c5b8011a3425a140bf5fa73be0feabd3c0d5b323eecb19dc02437a368ae075` |

---

## 2. Infrastructure & Service Health

All 6 containerized services were brought up via `docker compose up -d` and confirmed healthy via automated health checks:

- **API Gateway (`ekyc-api`):** Healthy on port `8005` (`GET http://127.0.0.1:8005/health` returned HTTP 200).
- **Background Worker (`ekyc-worker`):** Active daemon process connected to Redis stream consumer group `bank_submission_workers`.
- **Database (`ekyc-postgres`):** Healthy on port `5432`, accepting connections for `ekyc_db`.
- **Cache/Broker (`ekyc-redis`):** Healthy on port `6379`, responded to `PING` with `PONG`.
- **Fayda Sandbox (`ekyc-fayda-sandbox`):** Healthy on port `8081` (`GET http://127.0.0.1:8081/health` returned HTTP 200).
- **CBS Sandbox (`ekyc-cbs-sandbox`):** Healthy on port `8082` (`GET http://127.0.0.1:8082/health` returned HTTP 200).

---

## 3. Database Migration & Schema Verification

Database migrations were applied using Alembic against PostgreSQL in the running container:

- Target schema revision reached: **`13a9a8165587 (head)`** (`initial_ekyc_schema`).
- Verified zero migration errors or tracebacks; verified via `alembic current` and recorded in `release_evidence/migration_result.log`.

---

## 4. Broker Queue Inventory & Dead-Letter Baseline

- **Queue Name:** `bank_submission_queue`
  - **Consumer Group:** `bank_submission_workers`
  - **Connected Consumers:** 1 (`ekyc-worker`)
  - **Pending Messages:** 0
- **Dead-Letter Queue (`bank_submission_dlq`):**
  - **Baseline Message Count:** **0** (baseline verified clean for release).

---

## 5. External API Reachability

- **Fayda eKYC API Sandbox:** Reachable at `http://127.0.0.1:8081/fayda/v2` with `FAYDA_API_KEY`.
- **Bank CBS API Sandbox:** Reachable at `http://127.0.0.1:8082/cbs/v1` with `BANK_API_KEY`.

---

## 6. End-to-End Journey Smoke Test Results

All 8 critical user journeys from `journeys/` were smoke-tested against `http://127.0.0.1:8005` from outside the containers. Every request was tracked with a dedicated correlation ID and logged into `release_evidence/smoke_test_transcript.log`:

| Journey ID | Specification File | Correlation ID | Critical Path Tested | Status |
|---|---|---|---|---|
| **J-01** | `journeys/journey_01_account-opening.md` | `corr-smoke-j01-d670092d8cd0` | Full self-service account opening: Fayda OTP, biometric liveness, Awash Bank dynamic schema, queue dispatch, account issued | **PASSED** |
| **J-02** | `journeys/journey_02_consent-refusal.md` | `corr-smoke-j02-60f3db3b959f` | Citizen consent decline: transition to `CANCELLED`, zero PII stored, subsequent operations blocked with HTTP 403 | **PASSED** |
| **J-03** | `journeys/journey_03_fayda-format-lockout.md` | `corr-smoke-j03-d0d03e878d9f` | FIN format rejection (HTTP 422), 3 invalid OTP attempts triggering session lockout (HTTP 409 Conflict) | **PASSED** |
| **J-04** | `journeys/journey_04_otp-retry-fallback.md` | `corr-smoke-j04-7885c9871c1a` | First invalid OTP attempt returns HTTP 400 with remaining attempts counter; second attempt with valid OTP succeeds with `ID_VERIFIED` | **PASSED** |
| **J-05** | `journeys/journey_05_liveness-spoof-rejection.md` | `corr-smoke-j05-0265f6e909a9` | Presentation spoof attack (replay frame/photo) detected and rejected with HTTP 422 (`spoof_detected=true`) | **PASSED** |
| **J-06** | `journeys/journey_06_dynamic-fields-validation.md` | `corr-smoke-j06-44b840077127` | Missing required partner bank schema fields rejected with HTTP 400; complete dynamic fields validated with HTTP 200 | **PASSED** |
| **J-07** | `journeys/journey_07_bank-offline-retry.md` | `corr-smoke-j07-83da7e08674a` | Bank CBS 503 outage: worker records retry backoff while keeping application in `SUBMITTED_TO_BANK`; succeeds upon CBS recovery | **PASSED** |
| **J-08** | `journeys/journey_08_async-bank-callback.md` | `corr-smoke-j08-ca7378584aa4` | Asynchronous CBS batch clearance: HMAC-signed webhook callback accepted; application transitions from `BANK_ACCEPTED` to `ACCOUNT_OPENED` | **PASSED** |

---

## 7. Skipped Tests Audit

Ran static and dynamic skip analysis using `.vibearch/scripts/check_skipped_tests.py`:
- Test roots scanned: `tests/` (43 test files)
- Log scanned: `release_evidence/smoke_test_transcript.log`
- Result: **0 skipped tests, 0 pending tests, 0 ignored tests**. `release_evidence/skipped_tests_report.txt` is empty.

---

## 8. Anomalies & Hardening Interventions

1. **Audit Ledger Hash Chain Concurrency Serialization:**
   - *Observation:* During high-concurrency journey runs, parallel transactions read the same `prev_log_hash` before preceding transactions committed, creating a fork in the linear tamper-evident audit ledger.
   - *Remediation:* Integrated PostgreSQL transaction-level advisory locking (`SELECT pg_advisory_xact_lock(424242)`) in `src/services/audit.py:record_event`. Ledger appends are now strictly serialized and verifiable across all concurrent worker and API processes.
2. **Contract Parity for Consumer Event Deserialization:**
   - *Observation:* `check_parity.py --mode implementation` surfaced a missing consumer contract test for `application_submitted_event`.
   - *Remediation:* Implemented `tests/contract/test_application_submitted_event_consumer.py`, verifying JSON wire deserialization, forward compatibility with unmodeled fields, and constant-time HMAC signature verification.
3. **Fayda Sandbox Transaction State Accumulation:**
   - *Observation:* `VERIFICATION_FAILURES` state in `fayda_sandbox.py` was retained across test runs when reusing static FIN values.
   - *Remediation:* Added unique test run FIN generation in smoke test scripts to guarantee isolated failure tracking.

---

## 9. Release Evidence Bundle Manifest

The `release_evidence/` bundle is complete and verified:
```
release_evidence/
├── manifest.json              (versions, container digests, built timestamp)
├── smoke_test_transcript.log  (8 correlated user journeys, zero errors)
├── migration_result.log       (Alembic target head 13a9a8165587 reached)
├── queue_inventory.json       (bank_submission_queue, 1 active worker)
├── service_health.json        (6 services healthy)
├── external_api_status.json   (Fayda eKYC API & Bank CBS API reachable)
├── skipped_tests_report.txt   (empty, 0 skipped tests)
└── dlq_baseline.json          (0 messages in DLQ)
```
