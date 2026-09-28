"""
backend/db/session.py
Asynchronous database engine, session factory, and lifecycle initializer.
Supports both local SQLite (sqlite+aiosqlite) and cloud PostgreSQL (postgresql+asyncpg).
"""

from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import AsyncGenerator

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
                connect_args={"check_same_thread": False},
            )
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


async def init_db() -> None:
    """Creates database tables if they do not already exist."""
    from backend.db.models import Base

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


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
