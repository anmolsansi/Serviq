"""Serviq durable background-worker process composition."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, Callable

from app.core.broker import KafkaEventPublisher
from app.core.config import load_settings
from app.core.database import create_database_engine, create_database_session_factory
from app.jobs.outbox_publisher import publish_due_batch

_IDLE_POLL_SECONDS = 1.0


async def run_worker() -> None:
    """Continuously publish due PostgreSQL outbox rows until shutdown."""

    settings = load_settings()
    engine = create_database_engine(settings)
    session_factory = create_database_session_factory(engine)
    publisher = KafkaEventPublisher(settings)
    try:
        while True:
            async with session_factory() as session:
                processed = await publish_due_batch(session, publisher)
            if processed == 0:
                await asyncio.sleep(_IDLE_POLL_SECONDS)
    finally:
        publisher.close()
        await engine.dispose()


def main(
    *,
    runner: Callable[[Coroutine[Any, Any, None]], None] = asyncio.run,
) -> int:
    """Run the durable worker and translate operator interruption to clean exit."""

    try:
        runner(run_worker())
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
