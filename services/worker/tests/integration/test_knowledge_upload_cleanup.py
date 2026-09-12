from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import load_settings
from app.core.database import create_database_engine, create_database_session_factory
from app.core.object_storage import S3RawObjectStorage, build_object_storage
from app.jobs.knowledge_upload_cleanup import (
    KEY_MISMATCH_ERROR_CODE,
    PUT_OUTCOME_AMBIGUOUS_ERROR_CODE,
    reconcile_due_upload_cleanups,
)

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_KNOWLEDGE_CLEANUP_INTEGRATION") != "1",
    reason="requires real PostgreSQL and S3-compatible object storage",
)


async def _insert_cleanup(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    tenant_id: UUID,
    source_id: UUID,
    object_id: UUID,
    cleanup_id: UUID,
    object_key: str,
    status: str,
    attempt_count: int,
    next_attempt_at: datetime,
    last_error_code: str | None,
) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                """
                INSERT INTO knowledge_upload_cleanups (
                    id, tenant_id, source_id, object_id, object_key, status,
                    attempt_count, next_attempt_at, last_error_code
                ) VALUES (
                    :id, :tenant_id, :source_id, :object_id, :object_key, :status,
                    :attempt_count, :next_attempt_at, :last_error_code
                )
                """
            ),
            {
                "id": cleanup_id,
                "tenant_id": tenant_id,
                "source_id": source_id,
                "object_id": object_id,
                "object_key": object_key,
                "status": status,
                "attempt_count": attempt_count,
                "next_attempt_at": next_attempt_at,
                "last_error_code": last_error_code,
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO knowledge_upload_reservations (
                    id, tenant_id, source_id, reserved_bytes, cleanup_id, lease_expires_at
                ) VALUES (
                    :id, :tenant_id, :source_id, 64, :cleanup_id, :lease_expires_at
                )
                """
            ),
            {
                "id": uuid4(),
                "tenant_id": tenant_id,
                "source_id": source_id,
                "cleanup_id": cleanup_id,
                "lease_expires_at": next_attempt_at + timedelta(hours=1),
            },
        )


async def _create_tenant(
    session_factory: async_sessionmaker[AsyncSession],
) -> UUID:
    tenant_id = uuid4()
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                """
                INSERT INTO tenants (id, slug, display_name, status)
                VALUES (:id, :slug, 'Cleanup Worker Test', 'active')
                """
            ),
            {"id": tenant_id, "slug": f"cleanup-{tenant_id.hex[:12]}"},
        )
    return tenant_id


async def _state(
    session_factory: async_sessionmaker[AsyncSession], cleanup_id: UUID
) -> dict[str, object]:
    async with session_factory() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT status, attempt_count, next_attempt_at, last_error_code,
                           resolved_at,
                           EXISTS (
                               SELECT 1 FROM knowledge_upload_reservations r
                               WHERE r.cleanup_id = knowledge_upload_cleanups.id
                           ) AS has_reservation
                    FROM knowledge_upload_cleanups
                    WHERE id = :id
                    """
                ),
                {"id": cleanup_id},
            )
        ).mappings().one()
    return dict(row)


async def _delete_fixture(
    session_factory: async_sessionmaker[AsyncSession], tenant_id: UUID
) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(
            text("DELETE FROM knowledge_upload_reservations WHERE tenant_id=:tenant_id"),
            {"tenant_id": tenant_id},
        )
        await session.execute(
            text("DELETE FROM knowledge_upload_cleanups WHERE tenant_id=:tenant_id"),
            {"tenant_id": tenant_id},
        )
        await session.execute(
            text("DELETE FROM tenants WHERE id=:tenant_id"),
            {"tenant_id": tenant_id},
        )


def test_pending_cleanup_deletes_object_and_releases_reservation() -> None:
    async def scenario() -> None:
        settings = load_settings()
        engine = create_database_engine(settings)
        session_factory = create_database_session_factory(engine)
        storage = build_object_storage(settings)
        tenant_id = await _create_tenant(session_factory)
        source_id = uuid4()
        object_id = uuid4()
        cleanup_id = uuid4()
        key = f"tenants/{tenant_id}/knowledge/{source_id}/raw/{object_id}"
        now = datetime.now(UTC)
        try:
            await storage.put_bytes(key, b"orphan", content_type="text/plain")
            await _insert_cleanup(
                session_factory,
                tenant_id=tenant_id,
                source_id=source_id,
                object_id=object_id,
                cleanup_id=cleanup_id,
                object_key=key,
                status="pending",
                attempt_count=0,
                next_attempt_at=now - timedelta(seconds=1),
                last_error_code="KNOWLEDGE_SOURCE_PERSISTENCE_FAILED",
            )

            async with session_factory() as session:
                result = await reconcile_due_upload_cleanups(
                    session, storage, now=now, batch_size=10
                )

            assert result.processed == 1
            assert result.succeeded == 1
            assert await storage.exists(key) is False
            state = await _state(session_factory, cleanup_id)
            assert state["status"] == "succeeded"
            assert state["attempt_count"] == 1
            assert state["has_reservation"] is False
        finally:
            await storage.delete_object(key)
            await _delete_fixture(session_factory, tenant_id)
            await engine.dispose()

    asyncio.run(scenario())


def test_ambiguous_prepared_cleanup_recovers_after_restart() -> None:
    async def scenario() -> None:
        settings = load_settings()
        engine = create_database_engine(settings)
        session_factory = create_database_session_factory(engine)
        storage = build_object_storage(settings)
        tenant_id = await _create_tenant(session_factory)
        source_id = uuid4()
        object_id = uuid4()
        cleanup_id = uuid4()
        key = f"tenants/{tenant_id}/knowledge/{source_id}/raw/{object_id}"
        first_due = datetime.now(UTC)
        try:
            await _insert_cleanup(
                session_factory,
                tenant_id=tenant_id,
                source_id=source_id,
                object_id=object_id,
                cleanup_id=cleanup_id,
                object_key=key,
                status="prepared",
                attempt_count=0,
                next_attempt_at=first_due - timedelta(seconds=1),
                last_error_code=None,
            )

            async with session_factory() as session:
                first = await reconcile_due_upload_cleanups(
                    session, storage, now=first_due, batch_size=10
                )
            assert first.retry_scheduled == 1
            state_after_first = await _state(session_factory, cleanup_id)
            assert state_after_first["status"] == "pending"
            assert state_after_first["attempt_count"] == 1
            assert state_after_first["last_error_code"] == PUT_OUTCOME_AMBIGUOUS_ERROR_CODE
            next_attempt = state_after_first["next_attempt_at"]
            assert isinstance(next_attempt, datetime)

            # Simulate a later-visible object plus process restart: a fresh session
            # replays only durable DB state after the persisted lease becomes due.
            await storage.put_bytes(key, b"late-visible", content_type="text/plain")
            async with session_factory() as restarted_session:
                second = await reconcile_due_upload_cleanups(
                    restarted_session,
                    storage,
                    now=next_attempt + timedelta(seconds=1),
                    batch_size=10,
                )
            assert second.succeeded == 1
            state_after_restart = await _state(session_factory, cleanup_id)
            assert state_after_restart["status"] == "succeeded"
            assert state_after_restart["attempt_count"] == 2
            assert state_after_restart["has_reservation"] is False
            assert await storage.exists(key) is False
        finally:
            await storage.delete_object(key)
            await _delete_fixture(session_factory, tenant_id)
            await engine.dispose()

    asyncio.run(scenario())


def test_three_ambiguous_observations_exhaust_and_keep_reservation() -> None:
    async def scenario() -> None:
        settings = load_settings()
        engine = create_database_engine(settings)
        session_factory = create_database_session_factory(engine)
        storage: S3RawObjectStorage = build_object_storage(settings)
        tenant_id = await _create_tenant(session_factory)
        source_id = uuid4()
        object_id = uuid4()
        cleanup_id = uuid4()
        key = f"tenants/{tenant_id}/knowledge/{source_id}/raw/{object_id}"
        current = datetime.now(UTC)
        try:
            await _insert_cleanup(
                session_factory,
                tenant_id=tenant_id,
                source_id=source_id,
                object_id=object_id,
                cleanup_id=cleanup_id,
                object_key=key,
                status="prepared",
                attempt_count=0,
                next_attempt_at=current - timedelta(seconds=1),
                last_error_code=None,
            )

            for expected_attempt in (1, 2, 3):
                async with session_factory() as session:
                    result = await reconcile_due_upload_cleanups(
                        session, storage, now=current, batch_size=10
                    )
                state = await _state(session_factory, cleanup_id)
                assert state["attempt_count"] == expected_attempt
                if expected_attempt < 3:
                    assert result.retry_scheduled == 1
                    assert state["status"] == "pending"
                    next_attempt = state["next_attempt_at"]
                    assert isinstance(next_attempt, datetime)
                    current = next_attempt + timedelta(seconds=1)
                else:
                    assert result.exhausted == 1
                    assert state["status"] == "exhausted"
                    assert state["next_attempt_at"] is None
                    assert state["has_reservation"] is True
        finally:
            await _delete_fixture(session_factory, tenant_id)
            await engine.dispose()

    asyncio.run(scenario())


def test_key_mismatch_exhausts_without_touching_storage() -> None:
    async def scenario() -> None:
        settings = load_settings()
        engine = create_database_engine(settings)
        session_factory = create_database_session_factory(engine)
        storage = build_object_storage(settings)
        tenant_id = await _create_tenant(session_factory)
        source_id = uuid4()
        object_id = uuid4()
        cleanup_id = uuid4()
        wrong_key = f"tenants/{tenant_id}/knowledge/{source_id}/raw/{uuid4()}"
        now = datetime.now(UTC)
        try:
            await _insert_cleanup(
                session_factory,
                tenant_id=tenant_id,
                source_id=source_id,
                object_id=object_id,
                cleanup_id=cleanup_id,
                object_key=wrong_key,
                status="pending",
                attempt_count=0,
                next_attempt_at=now - timedelta(seconds=1),
                last_error_code="KNOWLEDGE_SOURCE_PERSISTENCE_FAILED",
            )
            async with session_factory() as session:
                result = await reconcile_due_upload_cleanups(
                    session, storage, now=now, batch_size=10
                )
            state = await _state(session_factory, cleanup_id)
            assert result.exhausted == 1
            assert state["status"] == "exhausted"
            assert state["attempt_count"] == 3
            assert state["last_error_code"] == KEY_MISMATCH_ERROR_CODE
            assert state["has_reservation"] is True
        finally:
            await _delete_fixture(session_factory, tenant_id)
            await engine.dispose()

    asyncio.run(scenario())
