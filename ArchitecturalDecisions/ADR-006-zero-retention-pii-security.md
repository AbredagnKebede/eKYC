# ADR-006: Zero-Retention PII and Biometric Data Security Architecture
status: accepted
spec_version: 1

## Context
Handling national identity documents and biometrics carries severe liability and strict regulatory obligations. The platform must prevent raw national identity number storage, prohibit cleartext PII at rest, and enforce zero permanent retention of biometric media once transmitted to the bank.

## Options
- **Option 1: Salted HMAC Hash + Ephemeral AES-256 Object Storage + Immediate Purge Lifecycle**: Fayda numbers stored only as salted HMAC-SHA256 hashes; demographic data encrypted via AES-256-GCM; biometric artifacts held in ephemeral encrypted storage with automatic hard deletion upon verified bank delivery.
- **Option 2: Persistent Media Vault**: Archiving selfies, biometric vectors, and national ID cards indefinitely for compliance audits. Violates stated platform non-goals and massively inflates security exposure.
- **Option 3: Cleartext Storage with Per-Table Disk Encryption**: Encrypts database blocks but leaves columns unencrypted in memory and database backups, failing field-level security mandates.

## Decision
Enforce **Salted HMAC-SHA256 hashing for Fayda identifiers**, **field-level AES-256-GCM encryption for stored demographic snapshots**, and an **immediate automated hard-deletion lifecycle for biometric media** upon receiving bank submission acknowledgment.

## Rationale
Cites `research/brainstorm.md` §Explicit Non-Goals (Non-Goal 3: "Permanent Biometric Archiving: The platform will not maintain a permanent database of biometric templates, selfies, or national ID photos; all biometric artifacts are purged post-dispatch") and `research/brainstorm.md` §Confirmed Intent (Bullet 13: "Zero Long-Term Biometric Storage").

## Consequences
- Data theft exposure is strictly minimized: a database breach yields neither raw national IDs nor recoverable biometric photos.
- Compliance with National Bank of Ethiopia (NBE) and international privacy frameworks (GDPR principle of storage limitation).
- Ephemeral storage requires strict cleanup hooks and background garbage-collection daemons for failed or abandoned sessions.
