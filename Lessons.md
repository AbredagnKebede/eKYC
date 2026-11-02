# Lessons
<!-- append: YYYY-MM-DD | <non-obvious insight only — skip the obvious> -->
2026-10-29 | In SQLAlchemy 2.0 with asyncpg under pytest, global async engine connection pools bind sockets to the event loop of the first calling test; multi-test async suites require session-scoped loops (asyncio_default_test_loop_scope = session) or explicit post-test engine disposal to avoid 'attached to a different loop' errors.
2026-11-02 | Fresh PostgreSQL containers initialize cluster storage and momentarily stop the temporary postmaster before the permanent instance listens; asynchronous database setup routines (e.g. init_models) should include brief retry loops with backoff to prevent transient ConnectionResetError on container boundary startup.
