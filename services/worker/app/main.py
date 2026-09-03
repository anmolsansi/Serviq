"""Serviq durable background-worker process composition."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.consumers.knowledge_sync import KnowledgeSyncConsumer
from app.core.broker import KafkaEventPublisher
from app.core.config import load_settings
from app.core.database import create_database_engine, create_database_session_factory
from app.core.object_storage import build_object_storage
from app.jobs.outbox_publisher import publish_due_batch

_IDLE_POLL_SECONDS = 1.0


async def _run_outbox_publisher(
    session_factory: async_sessionmaker[AsyncSession],
    publisher: KafkaEventPublisher,
) -> None:
    while True:
        async with session_factory() as session:
            processed = await publish_due_batch(session, publisher)
        if processed == 0:
            await asyncio.sleep(_IDLE_POLL_SECONDS)


async def run_worker() -> None:
    """Run durable outbox publication and knowledge-sync consumption together."""

    settings = load_settings()
    engine = create_database_engine(settings)
    session_factory = create_database_session_factory(engine)
    publisher = KafkaEventPublisher(settings)
    storage = build_object_storage(settings)
    knowledge_sync_consumer = KnowledgeSyncConsumer(
        settings,
        session_factory,
        storage,
        publisher,
    )
    try:
        async with asyncio.TaskGroup() as group:
            group.create_task(_run_outbox_publisher(session_factory, publisher))
            group.create_task(knowledge_sync_consumer.run_forever())
    finally:
        # TaskGroup has stopped both jobs before any shared runtime boundary closes.
        knowledge_sync_consumer.close()
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
