# Brainstorm & Intent Specification

## Confirmed Intent
status: user-approved
- Platform Role & Operating Boundaries: Operates strictly as a bank-partnered digital agent platform in Ethiopia; never holds accounts, holds customer funds, or manages balances.
- Phase 1 Pilot Scope: Focused exclusively on direct self-service customer onboarding on mobile (Android-first); Field Agent mode is formally deferred to Phase 3.
- Bank Selection & Dynamic Attributes: Customer selects a partner bank from an active registry; the app dynamically fetches and renders bank-specific fields (e.g., occupation, address, source of funds, nominee) and account tiers.
- Explicit Consent Gate: Mandatory, plain-language consent screen detailing data usage, recipient bank, and Fayda eKYC verification; must be accepted before any personal data is captured.
- Fayda Digital Identity Verification: Formats 12-digit FIN/FAN locally, then authenticates identity via Fayda / EthSwitch VeriFayda 2 (OTP/biometric); enforces lockout after consecutive failed attempts.
- Biometric Liveness & Facial Comparison: Captures live selfie with passive/active anti-spoofing and deepfake resistance, matched against the official photo returned by Fayda eKYC.
- Read-Only Verified Demographics: Demographic attributes (full name, DOB, gender) returned from Fayda eKYC are displayed as read-only; customer cannot alter identity fields.
- Verification Failure Fallback: Upon exhausting retry limits on Fayda OTP or selfie liveness, the app generates a persistent reference code and directs the user to the nearest physical branch of their selected bank.
- Digital Signature: Captures in-app touch signature or OTP e-sign before dispatching the application.
- Idempotent Bank Adapter Integration: Encapsulates bank-specific CBS APIs behind a unified `BankAdapter` contract with unique application UUIDs and salted-hash deduplication to prevent double-submissions.
- Strict State Machine Workflow: Applications transition strictly through: `DRAFT` → `CONSENTED` → `ID_VERIFIED` → `LIVENESS_PASSED` → `DATA_COMPLETE` → `SUBMITTED_TO_BANK` → `BANK_ACCEPTED` → `ACCOUNT_OPENED` → `ACTIVATED` (with explicit terminal failure states: `ID_FAILED`, `LIVENESS_FAILED`, `BANK_REJECTED`, `EXPIRED`, `CANCELLED`).
- Post-Account Issuance Experience: Displays the confirmed bank account number, assigned branch details, and clear activation/funding guidance for the bank's channels.
- Zero Long-Term Biometric Storage: Raw Fayda numbers are never stored in clear text (salted hashes only); selfies, facial liveness frames, and demographic photos are purged from encrypted temporary storage immediately upon verified hand-off to the bank.
- Tamper-Evident Audit & Compliance: Append-only audit logs for all consent events, verification transactions, and bank callbacks; hosted in-country in compliance with National Bank of Ethiopia (NBE) data localization directives.

## User-Facing Requirements
1. **Multilingual Localized Experience**: The mobile application must provide first-class support for English, Amharic, Afaan Oromo, and Tigrinya, with iconography and large tap targets accommodating first-time smartphone users.
2. **Bank Discovery & Account Tier Browsing**: Users can view all active participating partner banks, their available account tiers (e.g. Basic, Standard, Youth, Savings), and real-time operational status (online vs maintenance).
3. **Transparent Consent & Data Sharing Notice**: A clear plain-language consent modal explaining exactly what information will be requested from Fayda, who it will be shared with, and why.
4. **Fayda eKYC Authentication Flow**: Intuitive input for 12-digit FIN or FAN, followed by frictionless OTP verification or supported biometric challenge.
5. **Real-Time Interactive Liveness & Selfie**: Clear visual frame guiding the user to align their face, perform required micro-actions (e.g., blink/turn or passive flash check), and immediate quality feedback (lighting, glare, distance).
6. **Immutable Verified Review**: Display verified name, date of birth, and gender in read-only form to avoid fraud or accidental modification.
7. **Dynamic Bank Form Completion**: Dynamically rendered inputs tailored to the bank's schema requirements (e.g., source of funds, initial deposit pledge, nominee particulars).
8. **In-App Digital Signature**: Touch canvas signature or confirmation code capturing explicit intent to apply.
9. **Persistent Status Dashboard**: Real-time tracking of application lifecycle with clear push/SMS updates when moving from submission to bank acceptance and account activation.
10. **Graceful Failure Guidance**: Actionable fallback screens presenting reference numbers, nearest branch coordinates, and helpline details if verification fails or exceeds limits.

## Explicit Non-Goals
1. **Direct Account Custody or Funds Management**: The platform does not hold customer balances, open internal ledger accounts, process debits/credits, or act as an e-money issuer.
2. **Core Banking System Replacement**: The platform does not manage ledger balances, transactions, KYC tiers, or interest calculations; it interfaces strictly with each bank's CBS via an adapter.
3. **Permanent Biometric Archiving**: The platform will not maintain a permanent database of biometric templates, selfies, or national ID photos; all biometric artifacts are purged post-dispatch.
4. **Unregulated Third-Party Verification**: The platform does not use non-official third-party scraping or unofficial identity sources; verification is strictly anchored to official Fayda / VeriFayda 2 APIs.
5. **Phase 1 Field Agent Mode**: Field agent mobile roaming, offline multi-party caching, and supervisor approval loops are explicitly excluded from Phase 1 and deferred to Phase 3.

## Open Non-Technical Questions
1. **Relying Party Licensing**: Confirmation whether National ID Program (NIDP) allows third-party digital agents direct relying party status or requires all Fayda requests to originate from the partner bank's licensed gateway.
2. **Remote Onboarding Account Limits**: National Bank of Ethiopia (NBE) circular guidelines on transaction/balance limits for Tier 1 vs Tier 2 bank accounts opened via fully remote eKYC.
3. **Bank Billing & Activation SLAs**: Standardizing the operational definition of an "activated" account across partner banks (e.g., initial deposit within 30 days vs first transaction).
