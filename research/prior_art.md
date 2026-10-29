# Prior Art & Comparative Research

## Comparable Systems

### 1. MOSIP & e-Signet (Ethiopia Fayda Foundation)
- **Architecture**: Ethiopia's National ID Program (NIDP / Fayda) is built on MOSIP (Modular Open Source Identity Platform). MOSIP's e-Signet framework provides OIDC-compliant identity verification and eKYC services.
- **Key Takeaway**: Adopting MOSIP-aligned claim names and standard OIDC flow parameters ensures seamless alignment with NIDP specifications and EthSwitch VeriFayda 2 endpoints.

### 2. EthSwitch VeriFayda 2 Interoperability Layer
- **Architecture**: EthSwitch acts as Ethiopia's national financial switch and provides VeriFayda 2 as the central eKYC gateway connecting commercial banks to the Fayda database.
- **Key Takeaway**: Bank adapter flows must account for dual-mode connectivity: either our platform communicates with VeriFayda directly as a licensed agent, or our adapter formats an eKYC payload that the partner bank invokes via their existing VeriFayda connection.

### 3. India Stack eKYC & Bank Connector Platforms (Setu / Sandbox.co.in)
- **Architecture**: Unified API gateways that abstract heterogeneous Core Banking Systems (CBS) such as Finacle, BaNCS, and Flexcube for digital account opening.
- **Key Takeaway**: Core banking system APIs are notorious for varying response latencies, maintenance windows, and asynchronous AML hold states. A durable state machine with webhook handling, polling reconciliation, and dead-letter queues is essential.

### 4. Global Identity & Liveness Engines (Smile Identity, Persona, Onfido)
- **Architecture**: Modular onboarding engines combining client-side liveness guidance with server-side biometric verification and short-lived media retention.
- **Key Takeaway**: Passive liveness (anti-spoofing without complex user gymnastics) has vastly higher conversion rates on low-end devices and weak cameras than active liveness (head turns, blinking). Immediate client-side validation prevents uploading unparseable images.

---

## Reusable OSS Candidates

| Candidate & Version | License | What It Saves | Integration Risk & Mitigation |
|---|---|---|---|
| **FastAPI + Pydantic v2** | MIT | High-throughput asynchronous REST API, OpenAPI contract generation, strict typing and serialization for banking payloads. | Minimal risk. De-facto Python standard for modern microservices and APIs. |
| **SQLAlchemy 2.0 (Async) + PostgreSQL** | MIT / PostgreSQL | Robust relational persistence, ACID guarantees for the state machine, row-level locking (`FOR UPDATE`) for concurrent status mutations, and native `JSONB` for bank-specific dynamic forms. | Low risk. Standard enterprise relational stack. |
| **Redis + ARQ / Celery** | BSD-3-Clause / BSD | Fast distributed token storage, rate limiting, OTP attempt throttling, and asynchronous worker queues for idempotent bank submissions and retries. | Low risk. Well-understood operational model. |
| **Silent-Face-Anti-Spoofing / ONNX Runtime** | Apache 2.0 / MIT | Deepfake and photo/screen replay attack detection running on lightweight ONNX weights without external commercial vendor dependencies. | Medium risk. Model weights must be pruned and quantized (FP16/INT8) to ensure <500ms inference on standard server CPUs. |
| **Cryptography (pyca/cryptography)** | Apache 2.0 / BSD | Field-level AES-256-GCM encryption for temporary PII, SHA-256 salted hashing for Fayda IDs, and digital signature generation for bank dispatch payloads. | Very low risk. Industry gold standard cryptography library. |
| **XState / Transitions (Finite State Machine)** | MIT / BSD | Declarative specification of legal application state transitions, preventing invalid operations (e.g. submitting before consent or skipping liveness). | Minimal risk. Enforces deterministic business workflows. |

---

## Recommended Starting Posture

1. **Modular Architecture**:
   - Construct as a clean modular service:
     - `core/state_machine`: Governs state transitions, expirations, and transition invariants.
     - `services/identity`: Orchestrates Fayda eKYC verification and biometric anti-spoofing checks.
     - `services/bank_adapters`: Abstract `BankAdapter` interface with dynamic schema parsing and idempotent dispatch.
     - `services/audit`: Append-only, hash-chained audit logging service.
2. **Dynamic Bank Field Contract**:
   - Express bank-specific requirements as declarative JSONSchema structures allowing the client to dynamically render fields without mobile app code updates.
3. **Data Security & Zero-Trust Biometrics**:
   - Store raw Fayda identifiers solely as salted HMAC hashes.
   - Hold verification selfie frames and eKYC photos in memory or ephemeral AES-256 encrypted storage, purging them immediately upon bank acknowledgment.
4. **Resilient Mobile Client**:
   - Android-first client with multilingual support (Amharic, Afaan Oromo, Tigrinya, English), offline form draft storage, and low-bandwidth payload optimization.
