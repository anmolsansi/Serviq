from __future__ import annotations

import asyncio
import json
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.consumers.knowledge_sync import SYNC_TOPIC, KnowledgeSyncConsumer
from app.core.broker import KafkaEventPublisher
from app.core.config import load_settings
from app.core.database import create_database_engine, create_database_session_factory
from app.core.object_storage import build_object_storage

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_KNOWLEDGE_SYNC_INTEGRATION") != "1",
    reason="requires PostgreSQL, Redpanda, and S3-compatible storage",
)


async def _seed_source(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[UUID, UUID, UUID, str]:
    tenant_id = uuid4()
    user_id = uuid4()
    source_id = uuid4()
    object_key = f"tenants/{tenant_id}/knowledge/{source_id}/raw/{uuid4()}"
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO tenants (id, slug, display_name, status) "
                "VALUES (:id, :slug, 'E2E Tenant', 'active')"
            ),
            {"id": tenant_id, "slug": f"e2e-{tenant_id.hex[:12]}"},
        )
        await session.execute(
            text(
                """
                INSERT INTO users (
                    id, oidc_issuer, oidc_subject, email, display_name, status
                ) VALUES (
                    :id, 'https://e2e.invalid', :subject, :email,
                    'E2E Worker', 'active'
                )
                """
            ),
            {
                "id": user_id,
                "subject": f"e2e-{user_id}",
                "email": f"{user_id}@e2e.invalid",
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO knowledge_sources (
                    id, tenant_id, source_type, name, source_uri, object_key,
                    access_scope, status, sync_version, created_by
                ) VALUES (
                    :id, :tenant_id, 'text', 'E2E Runbook', NULL, :object_key,
                    'internal', 'syncing', 1, :created_by
                )
                """
            ),
            {
                "id": source_id,
                "tenant_id": tenant_id,
                "object_key": object_key,
                "created_by": user_id,
            },
        )
    return tenant_id, user_id, source_id, object_key


async def _wait_for_parse_event(
    session_factory: async_sessionmaker[AsyncSession],
    tenant_id: UUID,
) -> dict[str, object]:
    for _ in range(40):
        async with session_factory() as session:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT payload
                        FROM outbox_events
                        WHERE tenant_id=:tenant_id
                          AND event_type='serviq.knowledge.parse.v1'
                        LIMIT 1
                        """
                    ),
                    {"tenant_id": tenant_id},
                )
            ).mappings().one_or_none()
        if row is not None:
            payload = row["payload"]
            if isinstance(payload, dict):
                return payload
        await asyncio.sleep(0.25)
    raise AssertionError("knowledge sync parse event was not persisted")


async def _cleanup(
    session_factory: async_sessionmaker[AsyncSession],
    tenant_id: UUID,
    user_id: UUID,
    source_id: UUID,
) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(
            text("DELETE FROM outbox_events WHERE tenant_id=:tenant_id"),
            {"tenant_id": tenant_id},
        )
        await session.execute(
            text("DELETE FROM knowledge_documents WHERE source_id=:source_id"),
            {"source_id": source_id},
        )
        await session.execute(
            text("DELETE FROM knowledge_sources WHERE id=:source_id"),
            {"source_id": source_id},
        )
        await session.execute(
            text("DELETE FROM users WHERE id=:user_id"),
            {"user_id": user_id},
        )
        await session.execute(
            text("DELETE FROM tenants WHERE id=:tenant_id"),
            {"tenant_id": tenant_id},
        )


def test_real_file_sync_through_redpanda_s3_and_postgres() -> None:
    async def scenario() -> None:
        settings = load_settings()
        engine = create_database_engine(settings)
        session_factory = create_database_session_factory(engine)
        storage = build_object_storage(settings)
        publisher = KafkaEventPublisher(settings)
        consumer = KnowledgeSyncConsumer(settings, session_factory, storage, publisher)
        tenant_id, user_id, source_id, object_key = await _seed_source(session_factory)
        event_id = uuid4()
        payload_bytes = b"Serviq E2E knowledge sync payload"
        try:
            await storage.put_bytes(object_key, payload_bytes, content_type="text/plain")
            envelope = {
                "id": str(event_id),
                "eventType": SYNC_TOPIC,
                "schemaVersion": 1,
                "tenantId": str(tenant_id),
                "aggregateType": "knowledge_source",
                "aggregateId": str(source_id),
                "payload": {
                    "tenantId": str(tenant_id),
                    "sourceId": str(source_id),
                    "syncVersion": 1,
                },
                "correlationId": "e2e-request",
                "causationId": None,
            }
            await publisher.publish(
                topic=SYNC_TOPIC,
                key=str(source_id).encode(),
                value=json.dumps(envelope).encode(),
            )

            task = asyncio.create_task(consumer.run_forever())
            try:
                parse_payload = await _wait_for_parse_event(session_factory, tenant_id)
            finally:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task

            assert parse_payload["tenantId"] == str(tenant_id)
            assert parse_payload["sourceId"] == str(source_id)
            assert parse_payload["documentVersion"] == 1
            assert parse_payload["sourceType"] == "text"
            assert parse_payload["rawObjectKey"] == object_key

            async with session_factory() as session:
                document_count = (
                    await session.execute(
                        text(
                            "SELECT count(*) FROM knowledge_documents "
                            "WHERE tenant_id=:tenant_id AND source_id=:source_id"
                        ),
                        {"tenant_id": tenant_id, "source_id": source_id},
                    )
                ).scalar_one()
            assert document_count == 1
        finally:
            consumer.close()
            publisher.close()
            await _cleanup(session_factory, tenant_id, user_id, source_id)
            await engine.dispose()

    asyncio.run(scenario())
