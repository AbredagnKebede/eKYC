# Idea: eKYC Bank Onboarding Platform (Ethiopia)

## What it does
A bank-partnered digital onboarding platform and mobile application in Ethiopia that enables any individual to open a bank account at their chosen partner bank remotely without visiting a physical branch. The platform acts as an agent orchestrating identity verification and application submission: users select a partner bank, provide explicit consent, verify identity against the Fayda national digital ID database (via VeriFayda 2 / EthSwitch), complete facial liveness checks, fill bank-specific dynamic fields, sign, and submit. The platform securely dispatches the verified payload via an adapter layer to the chosen bank's Core Banking System (CBS) for account creation, tracking the application status through activation.

## Who it's for
- **End Customers**: Individuals in Ethiopia needing convenient, remote bank account opening on mobile devices across multiple regional languages (Amharic, Afaan Oromo, Tigrinya, English), optimized for low-end hardware and spotty network connectivity.
- **Field Agents**: Authorized agents assisting customers in person using agent mode (with offline capture and delayed sync capabilities).
- **Partner Banks**: Financial institutions looking to acquire verified, fraud-resistant retail customers through digital onboarding complying with National Bank of Ethiopia (NBE) regulatory standards.

## How it should behave
1. **Language & Bank Selection**: User selects a regional language and chooses a partner bank from the active partner registry, viewing supported account tiers and availability.
2. **Plain-Language Consent**: App presents a clear, mandatory consent screen disclosing data collection and transmission scope.
3. **Fayda ID Entry & Format Validation**: User enters their 12-digit Fayda FIN or FAN with immediate local format validation.
4. **Fayda eKYC Verification**: Platform triggers an authentication request with Fayda / EthSwitch using OTP, face match, or biometric verification, enforcing rate limits and lockouts on failed attempts.
5. **Liveness & Face Match**: User captures a live selfie evaluated against passive/active anti-spoofing and compared to the official Fayda credential photo.
6. **Read-Only Identity Review**: App displays pre-filled demographic data (full name, DOB, gender) returned directly by eKYC; the user cannot modify these verified attributes.
7. **Bank-Specific Dynamic Form**: App renders and captures additional fields required by the selected bank's dynamic schema (e.g., address, occupation, source of funds, nominee).
8. **Digital Signature & Idempotent Submission**: User signs digitally (in-app signature or OTP e-sign); the platform queues and transmits the verified payload to the bank adapter with unique idempotency keys and duplicate detection.
9. **Status Tracking & Account Issuance**: User monitors application progression through the state machine (`DRAFT` → `CONSENTED` → `ID_VERIFIED` → `LIVENESS_PASSED` → `DATA_COMPLETE` → `SUBMITTED_TO_BANK` → `BANK_ACCEPTED` → `ACCOUNT_OPENED` → `ACTIVATED`) until receiving their account number and activation instructions.

## Constraints and non-goals
- **Non-Goals**:
  - The platform does NOT hold deposits, manage user balances, issue credit, or replace bank core banking systems.
  - The platform does NOT store raw biometrics, selfies, or ID photos after hand-off confirmation.
- **Privacy & Data Security**:
  - Raw Fayda numbers are never stored in clear text; only salted hashes or bank references are retained.
  - Identity snapshots and temporary biometric artifacts reside in short-lived encrypted object storage and are purged upon bank receipt.
  - Append-only audit logs track all consent events, verification timestamps, and bank submissions.
- **Regulatory & Compliance**:
  - In-country hosting aligned with National Bank of Ethiopia (NBE) data localization directives and local data privacy frameworks.
- **Technical & Hardware Constraints**:
  - High resilience for low-end Android smartphones and high-latency/intermittent connectivity (resumable steps, lightweight bundle, local draft saving).
  - TLS 1.2+ transport security with certificate pinning, device binding, and token auth.

## Context
- **National Infrastructure Integrations**: Relies on Ethiopia's National ID Program (NIDP) Fayda eKYC and EthSwitch VeriFayda 2. Items marked `[CONFIRM]` in the technical draft (direct relying party access vs. bank-routed calls, permitted remote auth methods, tiered KYC caps, hosting rules) will be validated during consulting/architecture.
- **Bank Integrations**: Modular `BankAdapter` interface contract to decouple core onboarding orchestration from heterogenous bank APIs.
- **Delivery Scope**: Phase 1 pilot deliverable targeting the core backend state machine, one partner bank adapter, Android MVP client, and sandbox verification.
