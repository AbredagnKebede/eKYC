import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ekyc_db",
)

# Configure connection pooling with robust health checks and sensible pool limits
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
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


async def init_models() -> None:
    """Create all database tables defined in metadata."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_models() -> None:
    """Drop all database tables (used in integration test isolation)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
