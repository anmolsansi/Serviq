from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import IO, Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.core.config import load_settings
from app.core.database import create_database_engine, create_database_session_factory
from app.core.object_storage import ObjectStorageError, ObjectStorageKey, knowledge_raw_key
from app.modules.knowledge.cleanup import (
    KnowledgeUploadCleanupUnavailableError,
    arm_upload_cleanup,
    first_retry_due_at,
    reconcile_upload_cleanup,
)
from app.modules.knowledge.repository import (
    add_upload_cleanup_intent,
    count_upload_cleanups_by_status,
)
from tests.support.tenant_isolation import (
    TenantIsolationFixture,
    cleanup_tenant_isolation_fixture,
    seed_tenant_isolation_fixture,
)

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)


class CleanupStorage:
    def __init__(self, *, fail_delete: bool = False) -> None:
        self.fail_delete = fail_delete
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def put_object(
        self,
        key: ObjectStorageKey,
        data: bytes | IO[bytes],
        *,
        content_type: str,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        payload = data if isinstance(data, bytes) else data.read()
        self.objects[key.value] = payload

    def delete_object(self, key: ObjectStorageKey) -> None:
        self.deleted.append(key.value)
        if self.fail_delete:
            raise ObjectStorageError
        self.objects.pop(key.value, None)

    def get_object(self, key: ObjectStorageKey) -> Any:
        raise NotImplementedError

    def head(self, key: ObjectStorageKey) -> Any:
        raise NotImplementedError

    def exists(self, key: ObjectStorageKey) -> bool:
        return key.value in self.objects


async def _create_cleanup(
    session: Any,
    *,
    tenant_id: UUID,
    now: datetime,
    due_at: datetime,
) -> tuple[UUID, ObjectStorageKey]:
    cleanup_id = uuid4()
    source_id = uuid4()
    object_id = uuid4()
    key = knowledge_raw_key(
        tenant_id=tenant_id,
        source_id=source_id,
        object_id=object_id,
    )
    async with session.begin():
        add_upload_cleanup_intent(
            session,
            cleanup_id=cleanup_id,
            tenant_id=tenant_id,
            source_id=source_id,
            object_id=object_id,
            object_key=key.value,
            next_attempt_at=due_at,
            now=now,
        )
        await session.flush()
    return cleanup_id, key


def test_cleanup_replay_is_idempotent_tenant_safe_and_bounded(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        fixture = TenantIsolationFixture.new()
        seeded = False
        try:
            async with session_factory() as session, session.begin():
                await seed_tenant_isolation_fixture(session, fixture)
                seeded = True

            t0 = datetime(2026, 8, 24, 18, 0, tzinfo=UTC)

            # A due prepared record is deterministic crash/ambiguous-outcome recovery.
            storage = CleanupStorage()
            async with session_factory() as session:
                cleanup_id, key = await _create_cleanup(
                    session,
                    tenant_id=fixture.tenant_a,
                    now=t0 - timedelta(minutes=16),
                    due_at=t0 - timedelta(seconds=1),
                )
                storage.objects[key.value] = b"orphan"
                first = await reconcile_upload_cleanup(
                    session,
                    storage=storage,
                    tenant_id=fixture.tenant_a,
                    cleanup_id=cleanup_id,
                    now=t0,
                )
                assert first.outcome == "succeeded"
                assert first.attempt_count == 1
                assert storage.deleted == [key.value]
                assert storage.objects == {}

                replay = await reconcile_upload_cleanup(
                    session,
                    storage=storage,
                    tenant_id=fixture.tenant_a,
                    cleanup_id=cleanup_id,
                    now=t0 + timedelta(hours=1),
                )
                assert replay.outcome == "noop_succeeded"
                assert storage.deleted == [key.value]

            # Tenant-scoped lookup fails closed. It does not reveal or delete the key.
            foreign_storage = CleanupStorage()
            async with session_factory() as session:
                foreign_cleanup_id, foreign_key = await _create_cleanup(
                    session,
                    tenant_id=fixture.tenant_a,
                    now=t0,
                    due_at=t0,
                )
                foreign_storage.objects[foreign_key.value] = b"foreign"
                with pytest.raises(KnowledgeUploadCleanupUnavailableError):
                    await reconcile_upload_cleanup(
                        session,
                        storage=foreign_storage,
                        tenant_id=fixture.tenant_b,
                        cleanup_id=foreign_cleanup_id,
                        now=t0,
                    )
                assert foreign_storage.deleted == []
                assert foreign_key.value in foreign_storage.objects

            # Known failure arms the first retry at exactly 30 seconds.
            failing_storage = CleanupStorage(fail_delete=True)
            async with session_factory() as session:
                retry_cleanup_id, retry_key = await _create_cleanup(
                    session,
                    tenant_id=fixture.tenant_a,
                    now=t0,
                    due_at=t0 + timedelta(minutes=15),
                )
                failing_storage.objects[retry_key.value] = b"retry"
                await arm_upload_cleanup(
                    session,
                    tenant_id=fixture.tenant_a,
                    cleanup_id=retry_cleanup_id,
                    now=t0,
                )
                row = (
                    await session.execute(
                        text(
                            "SELECT status, attempt_count, next_attempt_at "
                            "FROM knowledge_upload_cleanups WHERE id=:id"
                        ),
                        {"id": retry_cleanup_id},
                    )
                ).one()
                assert row.status == "pending"
                assert row.attempt_count == 0
                assert row.next_attempt_at == first_retry_due_at(t0)
                await session.rollback()

                too_early = await reconcile_upload_cleanup(
                    session,
                    storage=failing_storage,
                    tenant_id=fixture.tenant_a,
                    cleanup_id=retry_cleanup_id,
                    now=t0 + timedelta(seconds=29),
                )
                assert too_early.outcome == "not_due"
                assert failing_storage.deleted == []

                attempt_1 = await reconcile_upload_cleanup(
                    session,
                    storage=failing_storage,
                    tenant_id=fixture.tenant_a,
                    cleanup_id=retry_cleanup_id,
                    now=t0 + timedelta(seconds=30),
                )
                assert attempt_1.outcome == "retry_scheduled"
                assert attempt_1.attempt_count == 1
                row = (
                    await session.execute(
                        text(
                            "SELECT status, next_attempt_at FROM knowledge_upload_cleanups "
                            "WHERE id=:id"
                        ),
                        {"id": retry_cleanup_id},
                    )
                ).one()
                assert row.status == "pending"
                assert row.next_attempt_at == t0 + timedelta(minutes=5, seconds=30)
                await session.rollback()

                attempt_2 = await reconcile_upload_cleanup(
                    session,
                    storage=failing_storage,
                    tenant_id=fixture.tenant_a,
                    cleanup_id=retry_cleanup_id,
                    now=t0 + timedelta(minutes=5, seconds=30),
                )
                assert attempt_2.outcome == "retry_scheduled"
                assert attempt_2.attempt_count == 2
                row = (
                    await session.execute(
                        text(
                            "SELECT next_attempt_at FROM knowledge_upload_cleanups WHERE id=:id"
                        ),
                        {"id": retry_cleanup_id},
                    )
                ).one()
                assert row.next_attempt_at == t0 + timedelta(minutes=35, seconds=30)
                await session.rollback()

                attempt_3 = await reconcile_upload_cleanup(
                    session,
                    storage=failing_storage,
                    tenant_id=fixture.tenant_a,
                    cleanup_id=retry_cleanup_id,
                    now=t0 + timedelta(minutes=35, seconds=30),
                )
                assert attempt_3.outcome == "exhausted"
                assert attempt_3.attempt_count == 3
                row = (
                    await session.execute(
                        text(
                            "SELECT status, next_attempt_at, resolved_at, last_error_code "
                            "FROM knowledge_upload_cleanups WHERE id=:id"
                        ),
                        {"id": retry_cleanup_id},
                    )
                ).one()
                assert row.status == "exhausted"
                assert row.next_attempt_at is None
                assert row.resolved_at is not None
                assert row.last_error_code == "OBJECT_STORAGE_UNAVAILABLE"
                assert failing_storage.deleted == [
                    retry_key.value,
                    retry_key.value,
                    retry_key.value,
                ]

                counts = await count_upload_cleanups_by_status(session)
                assert counts["succeeded"] >= 1
                assert counts["exhausted"] >= 1

            # The complete generated object key never appears in safe cleanup logs.
            assert retry_key.value not in caplog.text
        finally:
            if seeded:
                async with session_factory() as session, session.begin():
                    await session.execute(
                        text("DELETE FROM knowledge_upload_cleanups WHERE tenant_id IN (:a, :b)"),
                        {"a": fixture.tenant_a, "b": fixture.tenant_b},
                    )
                    await cleanup_tenant_isolation_fixture(session, fixture)
            await engine.dispose()

    asyncio.run(scenario())
