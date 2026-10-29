# Verification Checklist: loop_unit_02_cache-redis

- [ ] Implement asynchronous Redis client connection manager with reconnection backoff
- [ ] Implement sliding-window rate limiter using Redis sorted sets (zset)
- [ ] Implement ephemeral user session storage with 15-minute TTL enforcement
- [ ] Unit tests for rate limit calculation logic and session token serializing
- [ ] Integration tests verifying real Redis key expiry, TTL eviction, and rate-limiting enforcement
- [ ] Code coverage ≥ 85%
- [ ] Minimum 85% line coverage on target paths
- [ ] Meaningful assertions checked via check_assertions.py
- [ ] No silent mocks at critical boundaries (db)
