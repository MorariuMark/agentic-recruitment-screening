"""
backend/db/session.py
Asynchronous database engine, session factory, and lifecycle initializer.
Supports both local SQLite (sqlite+aiosqlite) and cloud PostgreSQL (postgresql+asyncpg).
"""

from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config import settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Returns or creates the global singleton async SQLAlchemy engine."""
    global _engine
    if _engine is None:
        db_url = settings.async_database_url
        is_sqlite = db_url.startswith("sqlite")

        if is_sqlite:
            # Ensure target directory exists for sqlite file
            if "///" in db_url:
                db_path = db_url.split("///", 1)[1]
                parent_dir = Path(db_path).parent
                if parent_dir and not parent_dir.exists():
                    parent_dir.mkdir(parents=True, exist_ok=True)

            _engine = create_async_engine(
                db_url,
                echo=False,
                connect_args={"check_same_thread": False, "timeout": 30.0},
            )

            @event.listens_for(_engine.sync_engine, "connect")
            def _set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute("PRAGMA journal_mode=WAL")
                    cursor.execute("PRAGMA busy_timeout=30000")
                except Exception:
                    pass
                finally:
                    cursor.close()
        else:
            # PostgreSQL (e.g. Neon, Supabase)
            _engine = create_async_engine(
                db_url,
                echo=False,
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20,
            )

    return _engine


def async_session_factory() -> async_sessionmaker[AsyncSession]:
    """Returns or initializes the async session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


@asynccontextmanager
async def async_session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for obtaining an async database session outside FastAPI dependency injection."""
    factory = async_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def _reconcile_sqlite_columns(sync_conn) -> None:
    """Auto-reconciles missing model columns on existing tables for SQLite."""
    from sqlalchemy import inspect, text
    from backend.db.models import Base

    try:
        inspector = inspect(sync_conn)
        for table_name, table in Base.metadata.tables.items():
            if not inspector.has_table(table_name):
                continue
            existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
            for column in table.columns:
                if column.name not in existing_cols:
                    col_type = column.type.compile(sync_conn.dialect)
                    sql = f"ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type} NULL"
                    try:
                        sync_conn.execute(text(sql))
                    except Exception:
                        pass
    except Exception:
        pass


async def init_db() -> None:
    """Creates database tables if they do not already exist and reconciles missing columns."""
    from backend.db.models import Base

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_reconcile_sqlite_columns)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session per request."""
    factory = async_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
