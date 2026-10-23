"""
tests/conftest.py
Global pytest fixtures and isolated test database setup.
Prevents unit tests from polluting the production screening.db database.
"""

import asyncio
import os
import tempfile
import socket
from pathlib import Path
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

# Isolate storage before application imports construct route-level singletons.
_TEST_STORAGE = Path(tempfile.mkdtemp(prefix="atos-pytest-"))
TEST_DB_FILE = str(_TEST_STORAGE / "screening.db")
TEST_DB_URL = f"sqlite+aiosqlite:///{Path(TEST_DB_FILE).as_posix()}"
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["CHROMA_DB_DIR"] = str(_TEST_STORAGE / "chroma")
os.environ["ENVIRONMENT"] = "test"
os.environ["AUTH_SECRET_FILE"] = str(_TEST_STORAGE / ".auth_session_secret")

from backend.config import settings
import backend.db.session as session_module
from backend.db.models import Base

@pytest.fixture(autouse=True)
def isolated_test_auth(monkeypatch):
    # Existing engine contracts are independent of login; auth tests opt into enforcement.
    monkeypatch.setattr(settings, "auth_required", False)


@pytest.fixture(autouse=True)
def reserved_test_hostnames(monkeypatch):
    """Mock reserved fixtures here, never fabricate DNS answers in production."""
    original = socket.getaddrinfo
    def resolve(host, port, *args, **kwargs):
        name = str(host).lower()
        if name in {"example.com", "test.com", "fa-test.fa.ocs.oraclecloud.com"} or name.endswith((".example.com", ".example", ".test", ".test.com", ".invalid")):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]
        return original(host, port, *args, **kwargs)
    monkeypatch.setattr(socket, "getaddrinfo", resolve)


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
