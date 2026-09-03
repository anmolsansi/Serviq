from __future__ import annotations

import asyncio
import json
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.broker import BrokerUnavailableError
from app.core.config import load_settings
from app.core.database import create_database_engine, create_database_session_factory
from app.jobs.outbox_publisher import publish_due_batch

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)


class RecordingPublisher:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.records: list[tuple[str, bytes, bytes]] = []

    async def publish(self, *, topic: str, key: bytes, value: bytes) -> None:
        if self.fail:
            raise BrokerUnavailableError
        self.records.append((topic, key, value))

    def close(self) -> None:
        return None


async def _insert_event(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    event_id: UUID,
    payload_json: str = '{"syncVersion": 1}',
) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                """
                INSERT INTO outbox_events (
                    id, tenant_id, event_type, schema_version, aggregate_type,
                    aggregate_id, payload, correlation_id, causation_id, status,
                    attempts, next_attempt_at
                ) VALUES (
                    :id, NULL, 'serviq.knowledge.sync.v1', 1, 'knowledge_source',
                    :aggregate_id, CAST(:payload AS jsonb), 'integration-request', NULL,
                    'pending', 0, now()
                )
                """
            ),
            {
                "id": event_id,
                "aggregate_id": str(event_id),
                "payload": payload_json,
            },
        )


async def _delete_event(
    session_factory: async_sessionmaker[AsyncSession], event_id: UUID
) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(text("DELETE FROM outbox_events WHERE id=:id"), {"id": event_id})


def test_success_retry_terminal_and_skip_locked_contracts() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        success_id = uuid4()
        retry_id = uuid4()
        invalid_id = uuid4()
        locked_id = uuid4()
        ids = (success_id, retry_id, invalid_id, locked_id)
        try:
            await _insert_event(session_factory, event_id=success_id)
            publisher = RecordingPublisher()
            async with session_factory() as session:
                processed = await publish_due_batch(session, publisher, batch_size=1)
            assert processed == 1
            assert len(publisher.records) == 1
            topic, key, value = publisher.records[0]
            assert topic == "serviq.knowledge.sync.v1"
            assert key == str(success_id).encode()
            assert json.loads(value)["id"] == str(success_id)

            async with session_factory() as session:
                success_state = (
                    await session.execute(
                        text(
                            "SELECT status, attempts, published_at "
                            "FROM outbox_events WHERE id=:id"
                        ),
                        {"id": success_id},
                    )
                ).one()
            assert success_state.status == "published"
            assert success_state.attempts == 0
            assert success_state.published_at is not None

            await _insert_event(session_factory, event_id=retry_id)
            async with session_factory() as session:
                processed = await publish_due_batch(
                    session,
                    RecordingPublisher(fail=True),
                    batch_size=1,
                )
            assert processed == 1
            async with session_factory() as session:
                retry_state = (
                    await session.execute(
                        text(
                            "SELECT status, attempts, next_attempt_at > now() AS delayed, "
                            "published_at FROM outbox_events WHERE id=:id"
                        ),
                        {"id": retry_id},
                    )
                ).one()
            assert retry_state.status == "pending"
            assert retry_state.attempts == 1
            assert retry_state.delayed is True
            assert retry_state.published_at is None

            await _insert_event(session_factory, event_id=invalid_id, payload_json="[]")
            async with session_factory() as session:
                processed = await publish_due_batch(session, RecordingPublisher(), batch_size=1)
            assert processed == 1
            async with session_factory() as session:
                invalid_state = (
                    await session.execute(
                        text("SELECT status, attempts FROM outbox_events WHERE id=:id"),
                        {"id": invalid_id},
                    )
                ).one()
            assert invalid_state.status == "failed"
            assert invalid_state.attempts == 1

            await _insert_event(session_factory, event_id=locked_id)
            async with session_factory() as locker:
                transaction = await locker.begin()
                await locker.execute(
                    text("SELECT id FROM outbox_events WHERE id=:id FOR UPDATE"),
                    {"id": locked_id},
                )
                competing = RecordingPublisher()
                async with session_factory() as session:
                    processed = await publish_due_batch(session, competing, batch_size=1)
                assert processed == 0
                assert competing.records == []
                await transaction.rollback()

            unlocked = RecordingPublisher()
            async with session_factory() as session:
                processed = await publish_due_batch(session, unlocked, batch_size=1)
            assert processed == 1
            assert len(unlocked.records) == 1
        finally:
            for event_id in ids:
                await _delete_event(session_factory, event_id)
            await engine.dispose()

    asyncio.run(scenario())
