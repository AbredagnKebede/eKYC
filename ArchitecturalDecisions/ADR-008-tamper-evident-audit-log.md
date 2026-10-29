# ADR-008: Tamper-Evident Append-Only Audit Logging
status: accepted
spec_version: 1

## Context
Regulatory compliance mandated by the National Bank of Ethiopia (NBE) and partner financial institutions requires an incontrovertible audit log of every consent grant, eKYC query, liveness outcome, and bank transmission. The audit records must be immutable, non-repudiable, and tamper-evident.

## Options
- **Option 1: Append-Only Relational Ledger with Cryptographic Hash Chaining (HMAC-SHA256)**: Each audit log entry includes the cryptographic digest of the prior entry, timestamp, actor ID, action enum, and an HMAC integrity signature verified with an isolated server key.
- **Option 2: Plain Application Logging (stdout / syslog / ELK)**: High throughput, but log files can be modified, truncated, or dropped without detection, failing regulatory non-repudiation standards.
- **Option 3: Public or Private Blockchain (Hyperledger / Ethereum)**: Excessive latency, high compute overhead, and unnecessary complexity for Phase 1 pilot requirements.

## Decision
Implement an **in-database append-only audit log table with SHA-256 hash chaining and HMAC integrity seals**, coupled with strict database role-level permissions (`INSERT` only, no `UPDATE` or `DELETE`).

## Rationale
Cites `research/brainstorm.md` §Confirmed Intent (Bullet 14: "Tamper-Evident Audit & Compliance: Append-only audit logs for all consent events, verification transactions, and bank callbacks") and `Idea_scaff.md` §Constraints and non-goals.

## Consequences
- Any unauthorized manual alteration or deletion of past audit records breaks the cryptographic hash chain and is immediately detectable.
- Database role separation ensures application workers can only append new audit entries without permission to alter historical rows.
- Straightforward extraction of compliance proof reports for bank auditors and NBE examiners.
