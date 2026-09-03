from __future__ import annotations

import asyncio
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
    mark_matching_source_failed,
    run_knowledge_sync,
)

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)


class _EmptyStorage:
    async def get_bytes(self, key: str) -> bytes:
        raise AssertionError(f"unexpected object read: {key}")

    async def put_bytes(self, key: str, data: bytes, *, content_type: str) -> None:
        raise AssertionError(f"unexpected object write: {key}")


async def _seed_source(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    source_type: str,
    source_uri: str | None,
    object_key: str | None,
) -> tuple[UUID, UUID, UUID]:
    tenant_id = uuid4()
    user_id = uuid4()
    source_id = uuid4()
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO tenants (id, slug, display_name, status) "
                "VALUES (:id, :slug, 'Failure Guard Tenant', 'active')"
            ),
            {"id": tenant_id, "slug": f"fg-{tenant_id.hex[:12]}"},
        )
        await session.execute(
            text(
                """
                INSERT INTO users (
                    id, oidc_issuer, oidc_subject, email, display_name, status
                ) VALUES (
                    :id, 'https://failure.invalid', :subject, :email,
                    'Failure Guard Worker', 'active'
                )
                """
            ),
            {
                "id": user_id,
                "subject": f"fg-{user_id}",
                "email": f"{user_id}@failure.invalid",
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO knowledge_sources (
                    id, tenant_id, source_type, name, source_uri, object_key,
                    access_scope, status, sync_version, created_by
                ) VALUES (
                    :id, :tenant_id, :source_type, 'Failure Guard Source',
                    :source_uri, :object_key, 'internal', 'syncing', 1, :created_by
                )
                """
            ),
            {
                "id": source_id,
                "tenant_id": tenant_id,
                "source_type": source_type,
                "source_uri": source_uri,
                "object_key": object_key,
                "created_by": user_id,
            },
        )
    return tenant_id, user_id, source_id


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


def test_sitemap_is_terminal_without_document_or_object_access() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        tenant_id, user_id, source_id = await _seed_source(
            session_factory,
            source_type="sitemap",
            source_uri="https://docs.example.com/sitemap.xml",
            object_key=None,
        )
        storage = cast(S3RawObjectStorage, _EmptyStorage())
        command = KnowledgeSyncCommand(
            event_id=uuid4(),
            tenant_id=tenant_id,
            source_id=source_id,
            sync_version=1,
            correlation_id="sitemap-test",
        )
        try:
            result = await run_knowledge_sync(session_factory, storage, command)

            assert result.completed is False
            assert result.retryable is False
            assert result.error_code == KnowledgeSyncErrorCode.SOURCE_TYPE_UNSUPPORTED
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
            assert document_count == 0
        finally:
            await _cleanup(session_factory, tenant_id, user_id, source_id)
            await engine.dispose()

    asyncio.run(scenario())


def test_failure_state_only_updates_matching_current_version() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        tenant_id = uuid4()
        source_id = uuid4()
        object_key = f"tenants/{tenant_id}/knowledge/{source_id}/raw/{uuid4()}"
        # Seed with the helper's generated IDs, then align the object key with its source.
        seeded_tenant_id, user_id, seeded_source_id = await _seed_source(
            session_factory,
            source_type="text",
            source_uri=None,
            object_key=object_key,
        )
        tenant_id = seeded_tenant_id
        source_id = seeded_source_id
        old_command = KnowledgeSyncCommand(
            event_id=uuid4(),
            tenant_id=tenant_id,
            source_id=source_id,
            sync_version=1,
            correlation_id="old-failure",
        )
        try:
            async with session_factory() as session, session.begin():
                await session.execute(
                    text(
                        "UPDATE knowledge_sources "
                        "SET sync_version=2, status='syncing', last_error_code=NULL "
                        "WHERE id=:source_id"
                    ),
                    {"source_id": source_id},
                )

            await mark_matching_source_failed(
                session_factory,
                old_command,
                "KNOWLEDGE_SOURCE_OBJECT_UNAVAILABLE",
            )
            async with session_factory() as session:
                stale_state = (
                    await session.execute(
                        text(
                            "SELECT status, sync_version, last_error_code "
                            "FROM knowledge_sources WHERE id=:source_id"
                        ),
                        {"source_id": source_id},
                    )
                ).mappings().one()
            assert stale_state["status"] == "syncing"
            assert stale_state["sync_version"] == 2
            assert stale_state["last_error_code"] is None

            current_command = KnowledgeSyncCommand(
                event_id=uuid4(),
                tenant_id=tenant_id,
                source_id=source_id,
                sync_version=2,
                correlation_id="current-failure",
            )
            await mark_matching_source_failed(
                session_factory,
                current_command,
                "KNOWLEDGE_SOURCE_OBJECT_UNAVAILABLE",
            )
            async with session_factory() as session:
                current_state = (
                    await session.execute(
                        text(
                            "SELECT status, sync_version, last_error_code "
                            "FROM knowledge_sources WHERE id=:source_id"
                        ),
                        {"source_id": source_id},
                    )
                ).mappings().one()
            assert current_state["status"] == "failed"
            assert current_state["sync_version"] == 2
            assert current_state["last_error_code"] == "KNOWLEDGE_SOURCE_OBJECT_UNAVAILABLE"
        finally:
            await _cleanup(session_factory, tenant_id, user_id, source_id)
            await engine.dispose()

    asyncio.run(scenario())
