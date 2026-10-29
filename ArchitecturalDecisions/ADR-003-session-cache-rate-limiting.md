# ADR-003: Distributed Session Cache and Rate Limiting
status: accepted
spec_version: 1

## Context
eKYC and OTP operations are vulnerable to brute-force attacks and enumeration. The platform requires sub-millisecond session validation, sliding-window rate limiting per device/IP/Fayda-hash, and short-lived OTP attempt tracking.

## Options
- **Option 1: Redis 7**: In-memory key-value store with native TTL expiration, atomic counters, and Redis scripting for sliding-window rate limiting.
- **Option 2: In-Memory In-Process Cache (e.g. cachetools)**: Simple to start, but fails when horizontal scaling to multiple backend container instances occurs.
- **Option 3: Memcached**: Fast caching; however, lacks complex data structures and atomic Lua scripting needed for sliding rate limit windows.

## Decision
Adopt **Redis 7** for ephemeral session management, sliding-window rate limiting, and OTP attempt tracking.

## Rationale
Cites `research/prior_art.md` §Reusable OSS Candidates ("Redis + ARQ / Celery: Fast distributed token storage, rate limiting, OTP attempt throttling, and asynchronous worker queues") and `research/brainstorm.md` §Confirmed Intent (Bullet 5: "authenticates identity via Fayda / EthSwitch VeriFayda 2 (OTP/biometric); enforces lockout after consecutive failed attempts").

## Consequences
- Guaranteed atomicity for OTP lockouts prevents race-condition brute-force attacks.
- Sub-millisecond auth token resolution offloads PostgreSQL.
- Ephemeral tokens naturally expire via TTL without requiring recurring database cleanup scripts.
