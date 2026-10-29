import pytest_asyncio
from src.models.base import engine

@pytest_asyncio.fixture(autouse=True)
async def cleanup_db_connections():
    yield
    await engine.dispose()
