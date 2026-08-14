"""Serviq API database engine and session ownership.

ADR-001 freezes one async SQLAlchemy pattern for the API. Repository and
service code must receive AsyncSession instances instead of creating engines.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import PlatformSettings, load_settings


class DatabaseConfigurationError(RuntimeError):
    """Safe database configuration error that never contains a raw URL."""


def sqlalchemy_database_url(settings: PlatformSettings) -> str:
    """Adapt the frozen DATABASE_URL to Serviq's Psycopg 3 SQLAlchemy dialect."""

    raw_url = str(settings.database_url)
    if raw_url.startswith("postgresql+psycopg://"):
        return raw_url
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
    raise DatabaseConfigurationError("DATABASE_URL must use the PostgreSQL scheme")


def create_database_engine(settings: PlatformSettings) -> AsyncEngine:
    """Create the API's async engine from validated platform settings."""

    return create_async_engine(
        sqlalchemy_database_url(settings),
        pool_pre_ping=True,
    )


def create_database_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create the one approved AsyncSession factory."""

    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@lru_cache(maxsize=1)
def get_database_engine() -> AsyncEngine:
    """Return the process-wide async engine, created lazily at first use."""

    return create_database_engine(load_settings())


@lru_cache(maxsize=1)
def get_database_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory bound to the process engine."""

    return create_database_session_factory(get_database_engine())


async def get_database_session() -> AsyncIterator[AsyncSession]:
    """Yield one request/work-unit session and always close it afterwards."""

    async with get_database_session_factory()() as session:
        yield session


async def dispose_database_engine() -> None:
    """Dispose the cached process engine, primarily for controlled shutdown/tests."""

    if get_database_engine.cache_info().currsize:
        await get_database_engine().dispose()
    get_database_session_factory.cache_clear()
    get_database_engine.cache_clear()
