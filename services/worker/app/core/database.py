"""Serviq worker database engine and session ownership."""

from __future__ import annotations

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
    """Adapt frozen DATABASE_URL to the repository-standard Psycopg 3 dialect."""

    raw_url = str(settings.database_url)
    if raw_url.startswith("postgresql+psycopg://"):
        return raw_url
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
    raise DatabaseConfigurationError("DATABASE_URL must use the PostgreSQL scheme")


def create_database_engine(settings: PlatformSettings) -> AsyncEngine:
    """Create the worker async engine from validated platform settings."""

    return create_async_engine(sqlalchemy_database_url(settings), pool_pre_ping=True)


def create_database_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create the one approved worker AsyncSession factory."""

    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@lru_cache(maxsize=1)
def get_database_engine() -> AsyncEngine:
    """Return the process-wide worker engine, created lazily."""

    return create_database_engine(load_settings())


@lru_cache(maxsize=1)
def get_database_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide worker session factory."""

    return create_database_session_factory(get_database_engine())


async def dispose_database_engine() -> None:
    """Dispose cached database resources during controlled shutdown."""

    if get_database_engine.cache_info().currsize:
        await get_database_engine().dispose()
    get_database_session_factory.cache_clear()
    get_database_engine.cache_clear()
