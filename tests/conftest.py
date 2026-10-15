"""
tests/conftest.py
Global pytest fixtures and isolated test database setup.
Prevents unit tests from polluting the production screening.db database.
"""

import asyncio
from pathlib import Path
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from backend.config import settings
import backend.db.session as session_module
from backend.db.models import Base

TEST_DB_FILE = "./data/test_pytest_isolated.db"
TEST_DB_URL = f"sqlite+aiosqlite:///{TEST_DB_FILE}"


@pytest.fixture(scope="session", autouse=True)
def isolate_test_database():
    """
    Directs all database transactions during pytest to an isolated test SQLite database.
    Preserves production data in ./data/screening.db.
    """
    Path("./data").mkdir(parents=True, exist_ok=True)
    if Path(TEST_DB_FILE).exists():
        try:
            Path(TEST_DB_FILE).unlink()
        except Exception:
            pass

    original_db_url = settings.database_url
    settings.database_url = TEST_DB_URL

    # Reset any existing engine
    session_module._engine = None
    session_module._session_factory = None

    # Pre-create all tables in the test database
    async def _create_tables():
        engine = session_module.get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        # If loop is already running, create a separate thread or runner
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            executor.submit(asyncio.run, _create_tables()).result()
    else:
        loop.run_until_complete(_create_tables())

    yield

    # Teardown: restore original settings and clean up test database file
    async def _teardown():
        if session_module._engine:
            await session_module._engine.dispose()
        session_module._engine = None
        session_module._session_factory = None

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                executor.submit(asyncio.run, _teardown()).result()
        else:
            loop.run_until_complete(_teardown())
    except Exception:
        pass

    settings.database_url = original_db_url
    if Path(TEST_DB_FILE).exists():
        try:
            Path(TEST_DB_FILE).unlink()
        except Exception:
            pass
