# ADR-007: Bank Adapter Contract and Idempotency Architecture
status: accepted
spec_version: 1

## Context
Commercial banks in Ethiopia operate heterogeneous Core Banking Systems (CBS) such as Finacle, Flexcube, and BaNCS with divergent API protocols (SOAP, REST, ISO 20022), fluctuating latency, and maintenance schedules. Submissions must never trigger duplicate account creation under network retries or transient CBS errors.

## Options
- **Option 1: Pluggable Adapter Pattern with Outbox Pattern & Salted Hash Deduplication**: Unified `BankAdapter` abstract class, unique application UUIDv4 idempotency keys, dual duplicate checks (salted Fayda hash + bank ID), and transactional outbox for reliable asynchronous delivery.
- **Option 2: Direct Synchronous Point-to-Point HTTP Calls**: Directly calling bank APIs from request handlers without an outbox or idempotency tracking. Network drops or timeout retry floods cause duplicate accounts and inconsistent application states.
- **Option 3: Enterprise Service Bus (ESB)**: Heavy external enterprise message bus (e.g. MuleSoft, IBM MQ). Overkill for Phase 1 pilot and adds high operational overhead.

## Decision
Implement a **Pluggable `BankAdapter` Interface** leveraging a **Transactional Outbox queue pattern** and **deterministic UUIDv4 + Salted Hash idempotency keys**.

## Rationale
Cites `research/prior_art.md` §Comparable Systems (System 3: "A durable state machine with webhook handling, polling reconciliation, and dead-letter queues is essential") and `research/brainstorm.md` §Confirmed Intent (Bullet 10: "Idempotent Bank Adapter Integration").

## Consequences
- New partner bank integrations require only writing an isolated adapter conforming to `BankAdapter`, with zero modifications to core state machine logic.
- Absolute protection against duplicate bank account generation during network reconnects or retry storms.
- Unreachable bank systems remain safely buffered in the outbox queue with exponential backoff and dead-letter queue escalation.
