# ADR-002: Relational Data Storage and State Machine Persistence
status: accepted
spec_version: 1

## Context
Applications progress through a strict finite state machine (`DRAFT` to `ACTIVATED`). The database must guarantee ACID isolation, prevent concurrent state collision through row-level locking, provide JSONB document flexibility for heterogeneous bank fields, and retain audit integrity.

## Options
- **Option 1: PostgreSQL 16 with Async SQLAlchemy & Alembic**: Battle-tested ACID transactions, native JSONB querying/indexing for dynamic schemas, and robust row-level locking (`SELECT ... FOR UPDATE`).
- **Option 2: MongoDB**: Flexible document model; however, lacking mature multi-document transaction semantics and relational consistency guarantees required for banking state machines.
- **Option 3: MySQL 8.0**: Mature relational engine; however, JSON capabilities and concurrent index locking for JSON documents are less mature than PostgreSQL.

## Decision
Adopt **PostgreSQL 16** managed via **Async SQLAlchemy 2.0** and **Alembic** migrations.

## Rationale
Cites `research/prior_art.md` §Reusable OSS Candidates ("SQLAlchemy 2.0 (Async) + PostgreSQL: Robust relational persistence, ACID guarantees for the state machine, row-level locking (FOR UPDATE) for concurrent status mutations, and native JSONB for bank-specific dynamic forms") and `research/brainstorm.md` §Confirmed Intent (Bullet 11: "Strict State Machine Workflow").

## Consequences
- Deterministic, atomic state transitions prevent duplicate application processing.
- Dynamic partner bank schemas are persisted safely in typed JSONB columns without requiring DDL alterations on every bank integration.
- Standard relational tooling simplifies backup, replication, and point-in-time recovery.
