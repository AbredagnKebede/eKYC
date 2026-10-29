# System Guide
spec_version: 1
frozen: true
amendments: see /spec_amendments/INDEX.md

## 1 Overview

### §1.1 Purpose and Operating Scope
The eKYC Bank Onboarding Platform provides a sovereign, secure, and resilient identity verification and onboarding conduit for Ethiopian retail banking. The platform functions strictly as an authorized digital onboarding agent, enabling individual retail customers to open fully verified accounts at any participating partner commercial bank without physically visiting a branch. The system orchestrates consent capture, Fayda national digital identity verification via EthSwitch VeriFayda 2, biometric anti-spoofing and face comparison, dynamic bank-specific form intake, and digital signatures. It packages verified applications into idempotent payloads dispatched to partner banks' Core Banking Systems (CBS).

### §1.2 Non-Goals and Boundary Enforcements
1. The platform does not hold deposits, maintain transactional ledgers, process customer funds, or issue credit lines.
2. The platform does not replace or duplicate any bank's Core Banking System (CBS).
3. The platform strictly prohibits permanent retention of biometric templates, selfies, facial vectors, or national ID photos once a verified application has been confirmed by the destination bank.
4. Raw 12-digit Fayda FIN or FAN identifiers are never persisted in plaintext.

### §1.3 Key Actors and UI Boundary
- **Customer**: End user operating the mobile application (`ui_mobile_app`) on Android or iOS.
- **Partner Bank**: Commercial financial institution receiving verified applications and issuing account numbers.
- **National ID Program (NIDP) & EthSwitch**: Authoritative eKYC providers verifying citizen identity and returning signed demographic profiles.

---

## 2 Data Model

### §2.1 Schema Architecture
The persistence tier (`db_postgres`) stores application metadata, encrypted demographic snapshots, and tamper-evident audit records using strict relational schemas:

- `applications`:
  - `id`: UUID Primary Key
  - `user_ref`: String (client device binding identifier)
  - `bank_id`: String (references active bank registry)
  - `tier`: String (e.g. `basic`, `standard`)
  - `status`: String Enum (`ApplicationStatus`)
  - `idempotency_hash`: String (HMAC-SHA256 salted hash of Fayda reference + bank_id)
  - `created_at`: Timestamp with time zone
  - `updated_at`: Timestamp with time zone
  - `expires_at`: Timestamp with time zone (default 24 hours from creation)

- `identity_snapshots`:
  - `application_id`: UUID Foreign Key references `applications(id)` ON DELETE CASCADE
  - `encrypted_full_name`: Bytea (AES-256-GCM encrypted)
  - `encrypted_dob`: Bytea (AES-256-GCM encrypted)
  - `gender`: String
  - `fayda_ref_hash`: String (HMAC-SHA256 salted hash)
  - `liveness_score`: Float
  - `verified_at`: Timestamp with time zone
  - `verification_method`: String Enum (`OTP`, `BIOMETRIC`)

- `consent_records`:
  - `id`: UUID Primary Key
  - `application_id`: UUID Foreign Key references `applications(id)`
  - `consent_version`: String
  - `accepted_at`: Timestamp with time zone
  - `ip_address`: String
  - `device_fingerprint`: String

- `bank_submissions`:
  - `id`: UUID Primary Key
  - `application_id`: UUID Foreign Key references `applications(id)`
  - `bank_id`: String
  - `dynamic_fields`: JSONB (bank-specific attributes)
  - `bank_reference`: String (nullable, returned by bank CBS)
  - `account_number`: String (nullable, issued account number)
  - `sent_at`: Timestamp with time zone
  - `last_attempt_at`: Timestamp with time zone
  - `retry_count`: Integer (default 0)
  - `error_message`: Text (nullable)

- `audit_logs`:
  - `id`: BigSerial Primary Key
  - `timestamp`: Timestamp with time zone
  - `actor_type`: String (`CUSTOMER`, `SYSTEM`, `WORKER`, `ADMIN`)
  - `actor_id`: String
  - `action`: String
  - `application_id`: UUID (nullable)
  - `payload_hash`: String (SHA-256)
  - `prev_log_hash`: String (SHA-256 cryptographic chain)
  - `hmac_signature`: String (HMAC-SHA256 seal)

### §2.2 Cryptographic Storage and Ephemeral Caching
- **PostgreSQL (`db_postgres`)**: Primary system of record for applications and audit logs.
- **Redis (`cache_redis`)**: Ephemeral storage for user sessions, OTP retry counters, sliding-window rate limiters, and the transactional outbox queue.
- **Biometric Ephemeral Buffer**: Temporary memory buffers held during active liveness checks, purged immediately upon dispatch.

---

## 3 APIs

### §3.1 REST API Surface (`api_gateway`)
All client interactions communicate through the `api_gateway` over TLS 1.2+ with bearer token authentication:

- `GET /v1/banks`: Retrieves the registry of active partner banks, operational status, supported account tiers, and JSONSchema for dynamic fields.
- `POST /v1/applications`: Initializes an onboarding application session; returns `application_id` and initial status `DRAFT`.
- `POST /v1/applications/{id}/consent`: Records explicit user consent with device metadata; transitions application to `CONSENTED`.
- `POST /v1/applications/{id}/identity/start`: Initiates Fayda verification session with 12-digit FIN/FAN; triggers OTP dispatch.
- `POST /v1/applications/{id}/identity/verify`: Submits citizen OTP; authenticates against Fayda eKYC; transitions application to `ID_VERIFIED`.
- `POST /v1/applications/{id}/liveness`: Evaluates live selfie frame stream against anti-spoofing engine and performs face match against Fayda photo; transitions application to `LIVENESS_PASSED`.
- `PUT /v1/applications/{id}/details`: Validates and persists bank-specific dynamic schema attributes; transitions application to `DATA_COMPLETE`.
- `POST /v1/applications/{id}/submit`: Captures digital signature and queues verified application into `bank_submission_queue`; transitions application to `SUBMITTED_TO_BANK`.
- `GET /v1/applications/{id}`: Returns real-time application status, assigned account number, and next steps.
- `POST /v1/webhooks/bank/{bank_id}`: Secure callback endpoint for partner banks to publish asynchronous status updates (HMAC signed).

### §3.2 Internal Services
- `api_gateway`: Ingress authentication, JWT verification, rate limiting, and route dispatch.
- `identity_service`: Orchestrates Fayda OIDC protocol, OTP challenge generation, and ONNX anti-spoofing inference.
- `bank_adapter_service`: Houses modular adapter implementations translating unified application models into specific bank CBS schemas.

### §3.3 External Integration APIs
- `fayda_ekyc_api`: The National ID Program (NIDP) eKYC gateway. Authenticates citizens using Fayda identifiers and returns signed demographic assertions.
  - Credential Env: `FAYDA_API_KEY`
  - Sandbox Endpoint: `FAYDA_SANDBOX_URL` (default: `http://127.0.0.1:8081/fayda/v2`)
- `bank_cbs_api`: Partner bank Core Banking System (e.g. Awash Bank Finacle API). Receives verified customer applications and returns confirmation account numbers.
  - Credential Env: `BANK_API_KEY`
  - Sandbox Endpoint: `BANK_CBS_SANDBOX_URL` (default: `http://127.0.0.1:8082/cbs/v1`)

---

## 4 State Machines

### §4.1 Application State Transitions
The core onboarding lifecycle is strictly enforced by the `onboarding_service`:

```
[START]
   │
   ▼
 DRAFT ──────────────► CONSENTED ──────────────► ID_VERIFIED
   │                      │                          │
   │ (reject)             │ (expire)                 │ (retry fail)
   ▼                      ▼                          ▼
 CANCELLED             EXPIRED                   ID_FAILED
                                                     │
                                                     ▼
 LIVENESS_PASSED ◄───────────────────────────────────┘
   │
   │ (spoof fail)
   ├───► LIVENESS_FAILED
   ▼
 DATA_COMPLETE
   │
   ▼
 SUBMITTED_TO_BANK ──► BANK_ACCEPTED ──► ACCOUNT_OPENED ──► ACTIVATED
   │                         │
   ▼                         ▼
 BANK_REJECTED         BANK_REJECTED
```

### §4.2 State Invariants and Guards
1. **Guard `CONSENTED`**: Application cannot initiate Fayda verification without an active, recorded consent entry matching current terms.
2. **Guard `ID_VERIFIED`**: Cannot upload selfie or evaluate liveness until demographic record is verified and hashed.
3. **Guard `LIVENESS_PASSED`**: Liveness score must exceed anti-spoofing threshold (0.90) and face cosine similarity must exceed 0.82.
4. **Guard `DATA_COMPLETE`**: Dynamic fields must validate against bank's active JSONSchema without unknown or missing required attributes.
5. **Guard `SUBMITTED_TO_BANK`**: Application payload must be cryptographically sealed and enqueued via transactional outbox.

---

## 5 Event Contracts

### §5.1 Event Topology
- **Message Queue**: `bank_submission_queue`
  - Managed via Redis Streams / List.
  - Enqueued by `onboarding_service` when user signs and submits.
  - Consumed by `bank_submission_worker`.
- **Worker Daemon**: `bank_submission_worker`
  - Runs entrypoint: `python -m src.workers.bank_submission`
  - Dequeues pending submissions, resolves appropriate `BankAdapter`, executes idempotent HTTP call to `bank_cbs_api`, and handles backoff.

### §5.2 Events
- `application_submitted_event`:
  - Publisher: `onboarding_service`
  - Consumer: `bank_submission_worker`
  - Schema:
    ```json
    {
      "event_name": "application_submitted_event",
      "application_id": "c4b3a1a0-7f24-4b5c-8d12-1f48f4a7c001",
      "bank_id": "bank_awash",
      "timestamp": "2026-10-28T15:00:00Z",
      "payload_signature": "sha256-hex-signature"
    }
    ```

- `application_status_updated_event`:
  - Publisher: `bank_submission_worker` or `api_gateway` (via webhook)
  - Consumer: `audit_service` and Notification subsystem
  - Schema:
    ```json
    {
      "event_name": "application_status_updated_event",
      "application_id": "c4b3a1a0-7f24-4b5c-8d12-1f48f4a7c001",
      "previous_status": "SUBMITTED_TO_BANK",
      "new_status": "ACCOUNT_OPENED",
      "account_number": "1000123456789",
      "timestamp": "2026-10-28T15:01:00Z"
    }
    ```

---

## 6 Security

### §6.1 Authentication and Device Binding
- Session tokens are short-lived HMAC-signed JWTs (15-minute TTL) bound to the client's device fingerprint.
- All network communication is enforced over TLS 1.2+ with public key certificate pinning in the mobile client.

### §6.2 Zero-Retention Biometric and Identity Security
- **Fayda FIN/FAN**: Never stored in plaintext; hashed via HMAC-SHA256 with a secret salt rotated per environment.
- **Demographic Snapshot**: Encrypted at rest using AES-256-GCM with keys stored in an isolated environment key vault.
- **Biometric Purge**: Raw face images and video frames are processed in volatile memory. Any temporary files written to ephemeral scratch storage are securely overwritten and unlinked immediately upon successful hand-off to the bank.

### §6.3 Cryptographic Audit Trail (`audit_service`)
- Every critical event (consent, verification attempt, submission, callback) writes an immutable record to `audit_logs`.
- Each audit row contains `prev_log_hash` computing SHA-256 over the previous row's contents, forming a verifiable append-only ledger sealed with an HMAC signature.

---

## 7 SLOs

### §7.1 Performance and Latency Targets
- **API Response Latency**: p95 < 250ms for core CRUD operations under nominal load.
- **Biometric Anti-Spoofing Inference**: p95 < 450ms for server-side ONNX liveness evaluation.
- **Bank Adapter Dispatch**: p95 < 1200ms for outbound CBS submission (excluding CBS internal processing).

### §7.2 Availability and Reliability
- **Platform Availability**: 99.9% uptime during operational banking windows.
- **State Transition Correctness**: 100% atomic transitions; zero orphan applications in indeterminate states.
- **Idempotency Guarantee**: 0 duplicate account submissions across retry storms or network drops.

---

## 8 Acceptance Scenarios

### 8.1 AS-01: Full End-to-End Self-Service Account Opening
- **Given**: Customer opens the mobile app, selects "Awash Bank", and accepts the plain-language consent screen.
- **When**: Customer enters valid 12-digit Fayda FIN, successfully verifies the received SMS OTP, passes the selfie liveness check, completes the dynamic bank form, and digitally signs.
- **Then**: Application transitions through `DRAFT` to `SUBMITTED_TO_BANK`, the bank adapter transmits the verified payload to `bank_cbs_api`, and the app receives and displays the generated bank account number and activation instructions.

### 8.2 AS-02: User Refuses Consent Halts Flow
- **Given**: Customer initiates application and reviews the consent screen.
- **When**: Customer declines or taps "Cancel".
- **Then**: Application state immediately transitions to `CANCELLED`, zero personal data or Fayda queries are dispatched, and the session terminates safely.

### 8.3 AS-03: Invalid Fayda National ID Format Lockout
- **Given**: Customer arrives at the Fayda entry screen.
- **When**: Customer enters an invalid format (non-12 digits or malformed checksum).
- **Then**: Client-side validation blocks submission; if forced via API, the backend rejects with HTTP 422, increments the rate-limit failure counter, and locks out the client after 5 consecutive failures.

### 8.4 AS-04: OTP Verification Retry Exhaustion Branch Fallback
- **Given**: Customer starts verification and receives an OTP challenge.
- **When**: Customer submits an incorrect OTP 3 consecutive times.
- **Then**: Application state transitions to `ID_FAILED`, further OTP attempts are rejected, and the app displays a persistent application reference code directing the customer to the nearest physical branch.

### 8.5 AS-05: Facial Liveness Spoof Detection Rejection
- **Given**: Customer is challenged for a live selfie after successful OTP verification.
- **When**: A static photograph or pre-recorded video screen replay is presented to the camera.
- **Then**: The ONNX anti-spoofing engine detects spoofing (score < 0.90), increments retry counter, and after 3 failures transitions application to `LIVENESS_FAILED` with referral to an in-person branch.

### 8.6 AS-06: Dynamic Bank Field Schema Validation Failure
- **Given**: Customer reaches the bank details entry step.
- **When**: Customer submits a payload omitting a mandatory bank field (e.g. `source_of_funds`) or submitting an invalid data type.
- **Then**: The API gateway validates against the bank's registered JSONSchema, rejects the request with HTTP 400 Problem Details, and prevents state advancement to `DATA_COMPLETE`.

### 8.7 AS-07: Idempotent Submission Handling Transient Bank Offline
- **Given**: Customer submits application, transitioning state to `SUBMITTED_TO_BANK`.
- **When**: Partner bank CBS API is temporarily unreachable (HTTP 503 / timeout).
- **Then**: `bank_submission_worker` catches the failure, keeps the application safely queued in the transactional outbox, retries with exponential backoff, and ensures no duplicate submission occurs when the bank recovers.

### 8.8 AS-08: Asynchronous Bank Callback and Account Number Issuance
- **Given**: Application is submitted and pending in `BANK_ACCEPTED` status awaiting AML review.
- **When**: Bank CBS triggers `POST /v1/webhooks/bank/{bank_id}` with valid HMAC signature containing `{ "status": "ACCOUNT_OPENED", "account_number": "1000987654321" }`.
- **Then**: The webhook handler updates application state to `ACCOUNT_OPENED`, stores the account number, appends an audit log entry, and notifies the customer.

---

## 9 Resilience and Failure Modes

### 9.1 Time-Dependent Behavior
- **CH-01: Client Session Token Expiry**:
  - Max TTL: 15 minutes.
  - Refresh Strategy: Silent sliding renewal on authenticated activity before expiry.
  - Behavior when expired: Immediate HTTP 401 Unauthorized; client prompts PIN/biometric re-authentication without losing draft progress.
- **CH-02: Fayda eKYC OTP Challenge Expiry**:
  - Max TTL: 180 seconds (3 minutes).
  - Refresh Strategy: Client must explicitly request "Resend OTP" (limited to 3 requests per 10 minutes).
  - Behavior when expired: Verification endpoint returns HTTP 410 Gone; OTP session is invalidated in `cache_redis`.
- **CH-03: Incomplete Application Draft Expiration**:
  - Max TTL: 24 hours from creation timestamp.
  - Refresh Strategy: None; drafts inactive after 24 hours are expired.
  - Behavior when expired: Background cleanup task marks status as `EXPIRED` and triggers cryptographic shredding of temporary artifacts.

### 9.2 Timeout and Retry Policy
- **CH-04: Fayda eKYC External Call Timeout**:
  - Timeout: 5000ms.
  - Retry Count: 2 retries with exponential backoff (initial delay 500ms, jitter 100ms).
  - Circuit Breaker: Tripped after 5 consecutive timeouts within 60 seconds; returns HTTP 504 Gateway Timeout with friendly maintenance guidance.
- **CH-05: Bank CBS Outbound Adapter Submission**:
  - Timeout: 8000ms.
  - Retry Count: 5 retries over 30 minutes with exponential backoff (`delay = 2^attempt * 5` seconds).
  - Circuit Breaker: Per-bank circuit breaker isolates failing banks while allowing healthy partner banks to continue processing applications.

### 9.3 Idempotency and Concurrency
- **CH-06: Duplicate Submission Race Condition**:
  - Idempotency Key: Client generates unique UUIDv4 `Idempotency-Key` header on submission.
  - Secondary Duplicate Lock: Deterministic hash computed as `HMAC-SHA256(fayda_hash, bank_id)`.
  - Duplicate Window: 30-day window enforced in database unique constraint `uq_fayda_bank_active`.
  - Concurrency Behavior: Database row-level locking (`SELECT ... FOR UPDATE`) guarantees only one transaction processes the state transition; concurrent attempts receive HTTP 409 Conflict with the active application state.

### 9.4 Partial Failure Scenarios
- **CH-07: Crash Between Database Transition and Message Enqueue**:
  - Pattern: Transactional Outbox. State mutation and outbox enqueue are committed within a single PostgreSQL ACID transaction.
  - Behavior: If worker crashes, unacknowledged outbox records remain in `db_postgres` and are automatically picked up by surviving worker instances.
- **CH-08: Bank CBS Permanent Rejection & Dead-Letter Escalation**:
  - Condition: Bank CBS returns non-retryable error (e.g. HTTP 400 Schema Mismatch or HTTP 403 Blacklisted Identity).
  - Compensation Strategy: Worker marks application as `BANK_REJECTED`, stores the specific CBS error code, logs an audit entry, and moves payload to the dead-letter queue (`bank_submission_dlq`) for administrative investigation.

---

## 10 Deployment

### §10.1 Artifact Manifest
All deployment targets and service containers are defined by the following build artifacts:
- `Dockerfile.api`: Container image for FastAPI backend application server and API gateway.
- `Dockerfile.worker`: Container image for background queue consumer daemon running `bank_submission_worker`.
- `docker-compose.yml`: Multi-container orchestration specification uniting all services, database, cache, and sandbox environments.

### §10.2 Service Specifications
1. **API Service (`ekyc-api`)**:
   - Compose Service Name: `api`
   - Build Target: `Dockerfile.api`
   - Health-Check Endpoint: `GET /health` (returns HTTP 200 `{ "status": "healthy" }`)
   - Required Environment Variables:
     - `DATABASE_URL`
     - `REDIS_URL`
     - `JWT_SECRET_KEY`
     - `HMAC_SALT_KEY`
     - `AES_MASTER_KEY`
     - `FAYDA_API_KEY`
     - `FAYDA_SANDBOX_URL`
     - `BANK_API_KEY`
     - `BANK_CBS_SANDBOX_URL`

2. **Worker Daemon (`ekyc-worker`)**:
   - Compose Service Name: `worker`
   - Build Target: `Dockerfile.worker`
   - Process Command: `python -m src.workers.bank_submission`
   - Health-Check: Internal heartbeat timestamp written to Redis key `worker:heartbeat` every 10 seconds.
   - Required Environment Variables: Same database and broker credentials as API service.

3. **Database & Infrastructure**:
   - Compose Service Name: `postgres` (Image: `postgres:16-alpine`)
   - Compose Service Name: `redis` (Image: `redis:7-alpine`)
   - Compose Service Name: `fayda-sandbox` (Mock Fayda eKYC HTTP service for journey testing)
   - Compose Service Name: `cbs-sandbox` (Mock Bank Core Banking System HTTP service for journey testing)
