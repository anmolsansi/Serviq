"""Dependency orchestration for Serviq API readiness."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.core.database import ping_database

DATABASE_READINESS_TIMEOUT_SECONDS = 2.0
logger = logging.getLogger("serviq.health")


async def database_is_ready(
    ping: Callable[[], Awaitable[None]] = ping_database,
    *,
    timeout_seconds: float = DATABASE_READINESS_TIMEOUT_SECONDS,
) -> bool:
    """Return whether PostgreSQL responds within the frozen readiness budget.

    Failures are normalized to a boolean here so the HTTP boundary cannot leak
    driver exceptions, connection strings, SQL text, or credentials.
    """

    try:
        async with asyncio.timeout(timeout_seconds):
            await ping()
    except TimeoutError:
        logger.warning("database_readiness_timeout")
        return False
    except Exception:  # noqa: BLE001 - dependency failures must normalize to readiness=false.
        logger.warning("database_readiness_failed")
        return False
    return True
