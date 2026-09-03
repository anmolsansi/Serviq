from __future__ import annotations

import asyncio
import hashlib
import os
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import load_settings
from app.core.database import create_database_engine, create_database_session_factory
from app.core.object_storage import S3RawObjectStorage
from app.jobs.knowledge_sync import (
    KnowledgeSyncCommand,
    KnowledgeSyncErrorCode,
    run_knowledge_sync,
)

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)


class MemoryStorage:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects
        self.writes: list[tuple[str, bytes, str]] = []

    async def get_bytes(self, key: str) -> bytes:
        return self.objects[key]

    async def put_bytes(self, key: str, data: bytes, *, content_type: str) -> None:
        self.objects[key] = data
        self.writes.append((key, data, content_type))


async def _create_fixture(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[UUID, UUID, UUID, str]:
    tenant_id = uuid4()
    user_id = uuid4()
    source_id = uuid4()
    object_key = f"tenants/{tenant_id}/knowledge/{source_id}/raw/{uuid4()}"
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                """
                INSERT INTO tenants (id, slug, display_name, status)
                VALUES (:id, :slug, 'Knowledge Sync Test', 'active')
                """
            ),
            {"id": tenant_id, "slug": f"ks-{tenant_id.hex[:12]}"},
        )
        await session.execute(
            text(
                """
                INSERT INTO users (
                    id, oidc_issuer, oidc_subject, email, display_name, status
                ) VALUES (
                    :id, 'https://integration.invalid', :subject, :email,
                    'Knowledge Sync Worker', 'active'
                )
                """
            ),
            {
                "id": user_id,
                "subject": f"ks-{user_id}",
                "email": f"{user_id}@integration.invalid",
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO knowledge_sources (
                    id, tenant_id, source_type, name, source_uri, object_key,
                    access_scope, status, sync_version, created_by
                ) VALUES (
                    :id, :tenant_id, 'text', 'Runbook', NULL, :object_key,
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


def test_file_sync_idempotency_versions_and_parse_handoff() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        tenant_id, user_id, source_id, object_key = await _create_fixture(session_factory)
        memory = MemoryStorage({object_key: b"alpha knowledge"})
        storage = cast(S3RawObjectStorage, memory)
        command = KnowledgeSyncCommand(
            event_id=uuid4(),
            tenant_id=tenant_id,
            source_id=source_id,
            sync_version=1,
            correlation_id="integration-sync-1",
        )
        try:
            result = await run_knowledge_sync(session_factory, storage, command)
            assert result.completed is True
            assert result.error_code is None

            async with session_factory() as session:
                document = (
                    await session.execute(
                        text(
                            """
                            SELECT id, canonical_uri, title, content_hash, document_version, status
                            FROM knowledge_documents
                            WHERE tenant_id=:tenant_id AND source_id=:source_id
                            """
                        ),
                        {"tenant_id": tenant_id, "source_id": source_id},
                    )
                ).mappings().one()
                parse_event = (
                    await session.execute(
                        text(
                            """
                            SELECT payload, correlation_id, causation_id
                            FROM outbox_events
                            WHERE tenant_id=:tenant_id
                              AND event_type='serviq.knowledge.parse.v1'
                            """
                        ),
                        {"tenant_id": tenant_id},
                    )
                ).mappings().one()
                source_state = (
                    await session.execute(
                        text(
                            """
                            SELECT status, last_synced_at, last_error_code
                            FROM knowledge_sources WHERE id=:source_id
                            """
                        ),
                        {"source_id": source_id},
                    )
                ).mappings().one()

            expected_hash = hashlib.sha256(b"alpha knowledge").hexdigest()
            assert document["canonical_uri"] is None
            assert document["title"] == "Runbook"
            assert document["content_hash"] == expected_hash
            assert document["document_version"] == 1
            assert document["status"] == "active"
            assert parse_event["correlation_id"] == "integration-sync-1"
            assert parse_event["causation_id"] == str(command.event_id)
            assert parse_event["payload"] == {
                "tenantId": str(tenant_id),
                "sourceId": str(source_id),
                "documentId": str(document["id"]),
                "documentVersion": 1,
                "sourceType": "text",
                "rawObjectKey": object_key,
                "canonicalUri": None,
                "contentHash": expected_hash,
            }
            assert source_state["status"] == "syncing"
            assert source_state["last_synced_at"] is not None
            assert source_state["last_error_code"] is None

            # Simulate a crash window from an older implementation or manual repair:
            # the document exists, but its durable parser obligation is missing.
            async with session_factory() as session, session.begin():
                await session.execute(
                    text(
                        """
                        DELETE FROM outbox_events
                        WHERE tenant_id=:tenant_id
                          AND event_type='serviq.knowledge.parse.v1'
                        """
                    ),
                    {"tenant_id": tenant_id},
                )

            replay = await run_knowledge_sync(session_factory, storage, command)
            assert replay.completed is True
            async with session_factory() as session:
                counts = (
                    await session.execute(
                        text(
                            """
                            SELECT
                              (
                                SELECT count(*)
                                FROM knowledge_documents
                                WHERE source_id=:source_id
                              ) AS documents,
                              (
                                SELECT count(*)
                                FROM outbox_events
                                WHERE tenant_id=:tenant_id
                                  AND event_type='serviq.knowledge.parse.v1'
                              ) AS parse_events
                            """
                        ),
                        {"source_id": source_id, "tenant_id": tenant_id},
                    )
                ).one()
            assert counts.documents == 1
            assert counts.parse_events == 1

            memory.objects[object_key] = b"different replay bytes"
            mismatch = await run_knowledge_sync(session_factory, storage, command)
            assert mismatch.completed is False
            assert mismatch.error_code == KnowledgeSyncErrorCode.REPLAY_CONTENT_MISMATCH

            async with session_factory() as session, session.begin():
                await session.execute(
                    text("UPDATE knowledge_sources SET sync_version=2 WHERE id=:source_id"),
                    {"source_id": source_id},
                )

            stale = await run_knowledge_sync(session_factory, storage, command)
            assert stale.completed is True
            assert stale.noop is True

            future = await run_knowledge_sync(
                session_factory,
                storage,
                KnowledgeSyncCommand(
                    event_id=uuid4(),
                    tenant_id=tenant_id,
                    source_id=source_id,
                    sync_version=3,
                    correlation_id="future",
                ),
            )
            assert future.completed is False
            assert future.error_code == KnowledgeSyncErrorCode.VERSION_AHEAD

            missing = await run_knowledge_sync(
                session_factory,
                storage,
                KnowledgeSyncCommand(
                    event_id=uuid4(),
                    tenant_id=uuid4(),
                    source_id=source_id,
                    sync_version=2,
                    correlation_id="cross-tenant",
                ),
            )
            assert missing.completed is False
            assert missing.error_code == KnowledgeSyncErrorCode.SOURCE_NOT_FOUND
        finally:
            await _cleanup(session_factory, tenant_id, user_id, source_id)
            await engine.dispose()

    asyncio.run(scenario())
