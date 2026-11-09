import asyncio
import os
from typing import AsyncGenerator
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


def normalize_database_url(raw: str) -> str:
    """Normalize provider URLs to asyncpg and strip libpq-only SSL query flags."""
    url = raw.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and not url.startswith("postgresql+asyncpg://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://") :]

    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    # asyncpg does not accept sslmode/channel_binding the same way as libpq
    for key in ("sslmode", "channel_binding"):
        query.pop(key, None)
    cleaned = parsed._replace(query=urlencode(query))
    return urlunparse(cleaned)


DATABASE_URL = normalize_database_url(
    os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ekyc_db",
    )
)

# Free-tier friendly pool defaults (override with env if needed)
_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "5"))

_connect_args = {}
# Render/Neon external hosts usually need TLS
_host = urlparse(DATABASE_URL).hostname or ""
if any(x in _host for x in (".render.com", ".neon.tech", "amazonaws.com")):
    _connect_args["ssl"] = True

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=_POOL_SIZE,
    max_overflow=_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=3600,
    connect_args=_connect_args,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""

    pass


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency helper yielding transactional async database sessions."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_models(retries: int = 5, delay: float = 1.0) -> None:
    """Create all database tables defined in metadata with connection retry."""
    # Ensure all model modules register tables on Base.metadata before create_all.
    import src.models.application  # noqa: F401
    import src.models.audit  # noqa: F401
    import src.models.bank_portal  # noqa: F401

    for attempt in range(retries):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            return
        except Exception:
            if attempt == retries - 1:
                raise
            await asyncio.sleep(delay)


async def drop_models() -> None:
    """Drop all database tables (used in integration test isolation)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
