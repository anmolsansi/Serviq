from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import IO, Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import load_settings
from app.core.database import (
    create_database_engine,
    create_database_session_factory,
    get_database_session,
)
from app.core.object_storage import ObjectStorageError, ObjectStorageKey
from app.core.principal import require_tenant_id, require_workforce_user_id
from app.main import app
from app.modules.knowledge import router as knowledge_router
from app.modules.knowledge import service as knowledge_service
from tests.support.tenant_isolation import (
    TenantIsolationFixture,
    cleanup_tenant_isolation_fixture,
    seed_tenant_isolation_fixture,
)

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)


class FakeStorage:
    def __init__(
        self,
        *,
        fail_put: bool = False,
        fail_after_put: bool = False,
        fail_delete: bool = False,
    ) -> None:
        self.fail_put = fail_put
        self.fail_after_put = fail_after_put
        self.fail_delete = fail_delete
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []
        self.metadata: dict[str, Mapping[str, str]] = {}

    def put_object(
        self,
        key: ObjectStorageKey,
        data: bytes | IO[bytes],
        *,
        content_type: str,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        if self.fail_put:
            raise ObjectStorageError
        payload = data if isinstance(data, bytes) else data.read()
        self.objects[key.value] = payload
        self.metadata[key.value] = dict(metadata or {})
        if self.fail_after_put:
            raise ObjectStorageError

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


def _install_overrides(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: UUID,
    tenant_id: UUID,
) -> None:
    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_database_session] = override_session
    app.dependency_overrides[require_workforce_user_id] = lambda: user_id
    app.dependency_overrides[require_tenant_id] = lambda: tenant_id


def _clear_overrides() -> None:
    app.dependency_overrides.clear()


async def _cleanup_count(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    tenant_id: UUID,
) -> int:
    async with session_factory() as session:
        return int(
            (
                await session.execute(
                    text(
                        "SELECT count(*) FROM knowledge_upload_cleanups "
                        "WHERE tenant_id=:tenant"
                    ),
                    {"tenant": tenant_id},
                )
            ).scalar_one()
        )


async def _make_cleanup_due(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    cleanup_id: UUID,
) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                "UPDATE knowledge_upload_cleanups "
                "SET next_attempt_at=:due, updated_at=:due "
                "WHERE id=:id AND status IN ('prepared','pending')"
            ),
            {
                "id": cleanup_id,
                "due": datetime.now(UTC) - timedelta(seconds=1),
            },
        )


def test_file_upload_durable_cleanup_consistency_and_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        fixture = TenantIsolationFixture.new()
        storage = FakeStorage()
        seeded = False
        try:
            async with session_factory() as session, session.begin():
                await seed_tenant_isolation_fixture(session, fixture)
                seeded = True

            monkeypatch.setattr(knowledge_router, "get_knowledge_object_storage", lambda: storage)
            _install_overrides(
                session_factory,
                user_id=fixture.owner_a,
                tenant_id=fixture.tenant_a,
            )
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

            # Happy path: intent exists before PUT, then source + referenced state commit.
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                created = await client.post(
                    "/api/v1/knowledge-sources",
                    data={
                        "sourceType": "text",
                        "name": "Uploaded help",
                        "accessScope": "customer",
                    },
                    files={"file": ("../../help.txt", b"safe support text", "text/plain")},
                )
                assert created.status_code == 201
                data = created.json()["data"]
                assert data["sourceType"] == "text"
                assert data["sourceUri"] is None
                assert data["status"] == "pending"
                assert data["syncVersion"] == 0
                assert data["lastErrorCode"] is None
                assert "objectKey" not in data
                assert "createdBy" not in data

            assert len(storage.objects) == 1
            key = next(iter(storage.objects))
            assert key.startswith(f"tenants/{fixture.tenant_a}/knowledge/")
            assert "/raw/" in key
            assert "help.txt" not in key
            assert storage.metadata[key]["original-filename"] == "help.txt"

            async with session_factory() as session:
                source_row = (
                    await session.execute(
                        text(
                            "SELECT object_key, source_uri, status, sync_version, last_error_code "
                            "FROM knowledge_sources WHERE id=:id AND tenant_id=:tenant"
                        ),
                        {"id": UUID(data["id"]), "tenant": fixture.tenant_a},
                    )
                ).one()
                cleanup_row = (
                    await session.execute(
                        text(
                            "SELECT object_key, status, attempt_count, next_attempt_at, resolved_at "
                            "FROM knowledge_upload_cleanups "
                            "WHERE source_id=:source AND tenant_id=:tenant"
                        ),
                        {"source": UUID(data["id"]), "tenant": fixture.tenant_a},
                    )
                ).one()
                assert source_row.object_key == key
                assert source_row.source_uri is None
                assert source_row.status == "pending"
                assert source_row.sync_version == 0
                assert source_row.last_error_code is None
                assert cleanup_row.object_key == key
                assert cleanup_row.status == "referenced"
                assert cleanup_row.attempt_count == 0
                assert cleanup_row.next_attempt_at is None
                assert cleanup_row.resolved_at is not None

            # Permission and foreign-tenant denial occur before intent or object creation.
            baseline_a = await _cleanup_count(session_factory, tenant_id=fixture.tenant_a)
            object_count = len(storage.objects)
            _install_overrides(
                session_factory,
                user_id=fixture.member_a,
                tenant_id=fixture.tenant_a,
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                denied = await client.post(
                    "/api/v1/knowledge-sources",
                    data={"sourceType": "text", "name": "Denied", "accessScope": "customer"},
                    files={"file": ("denied.txt", b"no", "text/plain")},
                )
                assert denied.status_code == 403
            assert await _cleanup_count(session_factory, tenant_id=fixture.tenant_a) == baseline_a
            assert len(storage.objects) == object_count

            _install_overrides(
                session_factory,
                user_id=fixture.owner_a,
                tenant_id=fixture.tenant_b,
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                foreign_denied = await client.post(
                    "/api/v1/knowledge-sources",
                    data={
                        "sourceType": "text",
                        "name": "Foreign tenant denied",
                        "accessScope": "customer",
                    },
                    files={"file": ("foreign.txt", b"no", "text/plain")},
                )
                assert foreign_denied.status_code == 403
            assert await _cleanup_count(session_factory, tenant_id=fixture.tenant_b) == 0
            assert len(storage.objects) == object_count

            # PUT failure + successful immediate idempotent delete leaves no source and
            # a terminal succeeded cleanup record instead of a tenant-visible failed row.
            failing_storage = FakeStorage(fail_put=True)
            monkeypatch.setattr(
                knowledge_router,
                "get_knowledge_object_storage",
                lambda: failing_storage,
            )
            _install_overrides(
                session_factory,
                user_id=fixture.owner_a,
                tenant_id=fixture.tenant_a,
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                failed = await client.post(
                    "/api/v1/knowledge-sources",
                    data={"sourceType": "text", "name": "Storage fail", "accessScope": "customer"},
                    files={"file": ("fail.txt", b"safe", "text/plain")},
                )
                assert failed.status_code == 503
            assert failing_storage.objects == {}
            assert len(failing_storage.deleted) == 1
            async with session_factory() as session:
                assert (
                    await session.execute(
                        text(
                            "SELECT count(*) FROM knowledge_sources "
                            "WHERE tenant_id=:tenant AND name='Storage fail'"
                        ),
                        {"tenant": fixture.tenant_a},
                    )
                ).scalar_one() == 0
                failed_cleanup = (
                    await session.execute(
                        text(
                            "SELECT status, attempt_count, next_attempt_at, resolved_at "
                            "FROM knowledge_upload_cleanups "
                            "WHERE tenant_id=:tenant ORDER BY created_at DESC, id DESC LIMIT 1"
                        ),
                        {"tenant": fixture.tenant_a},
                    )
                ).one()
                assert failed_cleanup.status == "succeeded"
                assert failed_cleanup.attempt_count == 0
                assert failed_cleanup.next_attempt_at is None
                assert failed_cleanup.resolved_at is not None

            # Ambiguous PUT + delete failure proves the original double-failure path.
            ambiguous_storage = FakeStorage(fail_after_put=True, fail_delete=True)
            monkeypatch.setattr(
                knowledge_router,
                "get_knowledge_object_storage",
                lambda: ambiguous_storage,
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                ambiguous = await client.post(
                    "/api/v1/knowledge-sources",
                    data={
                        "sourceType": "text",
                        "name": "Ambiguous storage outcome",
                        "accessScope": "customer",
                    },
                    files={"file": ("ambiguous.txt", b"safe", "text/plain")},
                )
                assert ambiguous.status_code == 503
            assert len(ambiguous_storage.objects) == 1
            ambiguous_key = next(iter(ambiguous_storage.objects))
            async with session_factory() as session:
                ambiguous_cleanup = (
                    await session.execute(
                        text(
                            "SELECT id, object_key, status, attempt_count, next_attempt_at "
                            "FROM knowledge_upload_cleanups "
                            "WHERE tenant_id=:tenant ORDER BY created_at DESC, id DESC LIMIT 1"
                        ),
                        {"tenant": fixture.tenant_a},
                    )
                ).one()
                assert ambiguous_cleanup.object_key == ambiguous_key
                assert ambiguous_cleanup.status == "pending"
                assert ambiguous_cleanup.attempt_count == 0
                assert ambiguous_cleanup.next_attempt_at is not None
                ambiguous_cleanup_id = UUID(str(ambiguous_cleanup.id))
                assert (
                    await session.execute(
                        text(
                            "SELECT count(*) FROM knowledge_sources "
                            "WHERE tenant_id=:tenant AND name='Ambiguous storage outcome'"
                        ),
                        {"tenant": fixture.tenant_a},
                    )
                ).scalar_one() == 0

            # Foreign-tenant replay cannot claim the row or reach object storage.
            deletes_before_foreign_replay = len(ambiguous_storage.deleted)
            async with session_factory() as session:
                foreign_replay = await knowledge_service.reconcile_file_upload_cleanup(
                    session,
                    storage=ambiguous_storage,
                    tenant_id=fixture.tenant_b,
                    cleanup_id=ambiguous_cleanup_id,
                    now=datetime.now(UTC) + timedelta(hours=1),
                )
            assert foreign_replay == "not_due"
            assert len(ambiguous_storage.deleted) == deletes_before_foreign_replay

            # Restore storage, replay once, and prove idempotent convergence.
            ambiguous_storage.fail_delete = False
            await _make_cleanup_due(session_factory, cleanup_id=ambiguous_cleanup_id)
            async with session_factory() as session:
                replayed = await knowledge_service.reconcile_file_upload_cleanup(
                    session,
                    storage=ambiguous_storage,
                    tenant_id=fixture.tenant_a,
                    cleanup_id=ambiguous_cleanup_id,
                )
            assert replayed == "succeeded"
            assert ambiguous_storage.objects == {}
            async with session_factory() as session:
                replayed_row = (
                    await session.execute(
                        text(
                            "SELECT status, attempt_count, next_attempt_at, resolved_at "
                            "FROM knowledge_upload_cleanups WHERE id=:id"
                        ),
                        {"id": ambiguous_cleanup_id},
                    )
                ).one()
                assert replayed_row.status == "succeeded"
                assert replayed_row.attempt_count == 1
                assert replayed_row.next_attempt_at is None
                assert replayed_row.resolved_at is not None

            # Successful PUT + source-DB failure + delete failure remains durable.
            persistence_storage = FakeStorage(fail_delete=True)
            monkeypatch.setattr(
                knowledge_router,
                "get_knowledge_object_storage",
                lambda: persistence_storage,
            )

            def fail_source_database(*args: Any, **kwargs: Any) -> Any:
                raise RuntimeError("synthetic source database failure")

            with monkeypatch.context() as source_patch:
                source_patch.setitem(
                    knowledge_service.__dict__,
                    "add_file_knowledge_source",
                    fail_source_database,
                )
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    failed_db = await client.post(
                        "/api/v1/knowledge-sources",
                        data={
                            "sourceType": "text",
                            "name": "Source persistence fail",
                            "accessScope": "customer",
                        },
                        files={"file": ("db.txt", b"safe", "text/plain")},
                    )
                    assert failed_db.status_code == 500
            assert len(persistence_storage.objects) == 1
            persistence_key = next(iter(persistence_storage.objects))
            async with session_factory() as session:
                persistence_cleanup = (
                    await session.execute(
                        text(
                            "SELECT id, object_key, status, attempt_count "
                            "FROM knowledge_upload_cleanups "
                            "WHERE tenant_id=:tenant ORDER BY created_at DESC, id DESC LIMIT 1"
                        ),
                        {"tenant": fixture.tenant_a},
                    )
                ).one()
                assert persistence_cleanup.object_key == persistence_key
                assert persistence_cleanup.status == "pending"
                assert persistence_cleanup.attempt_count == 0
                assert (
                    await session.execute(
                        text(
                            "SELECT count(*) FROM knowledge_sources "
                            "WHERE tenant_id=:tenant AND name='Source persistence fail'"
                        ),
                        {"tenant": fixture.tenant_a},
                    )
                ).scalar_one() == 0

            # Bounded retry reaches an operator-visible exhausted state after 3 attempts.
            exhausted_storage = FakeStorage(fail_after_put=True, fail_delete=True)
            monkeypatch.setattr(
                knowledge_router,
                "get_knowledge_object_storage",
                lambda: exhausted_storage,
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                exhausted_request = await client.post(
                    "/api/v1/knowledge-sources",
                    data={
                        "sourceType": "text",
                        "name": "Exhaust cleanup",
                        "accessScope": "customer",
                    },
                    files={"file": ("exhaust.txt", b"safe", "text/plain")},
                )
                assert exhausted_request.status_code == 503
            async with session_factory() as session:
                exhausted_cleanup_id = UUID(
                    str(
                        (
                            await session.execute(
                                text(
                                    "SELECT id FROM knowledge_upload_cleanups "
                                    "WHERE tenant_id=:tenant "
                                    "ORDER BY created_at DESC, id DESC LIMIT 1"
                                ),
                                {"tenant": fixture.tenant_a},
                            )
                        ).scalar_one()
                    )
                )

            expected_outcomes = ("retry_scheduled", "retry_scheduled", "exhausted")
            for expected in expected_outcomes:
                await _make_cleanup_due(session_factory, cleanup_id=exhausted_cleanup_id)
                async with session_factory() as session:
                    outcome = await knowledge_service.reconcile_file_upload_cleanup(
                        session,
                        storage=exhausted_storage,
                        tenant_id=fixture.tenant_a,
                        cleanup_id=exhausted_cleanup_id,
                    )
                assert outcome == expected

            async with session_factory() as session:
                exhausted_row = (
                    await session.execute(
                        text(
                            "SELECT status, attempt_count, next_attempt_at, resolved_at "
                            "FROM knowledge_upload_cleanups WHERE id=:id"
                        ),
                        {"id": exhausted_cleanup_id},
                    )
                ).one()
                assert exhausted_row.status == "exhausted"
                assert exhausted_row.attempt_count == 3
                assert exhausted_row.next_attempt_at is None
                assert exhausted_row.resolved_at is not None
                counts = await knowledge_service.get_file_upload_cleanup_status_counts(session)
                assert counts["exhausted"] >= 1

            # If the pre-PUT durable intent cannot commit, storage is never touched.
            registration_storage = FakeStorage()
            monkeypatch.setattr(
                knowledge_router,
                "get_knowledge_object_storage",
                lambda: registration_storage,
            )

            def fail_cleanup_database(*args: Any, **kwargs: Any) -> Any:
                raise RuntimeError("synthetic cleanup-intent database failure")

            with monkeypatch.context() as cleanup_patch:
                cleanup_patch.setitem(
                    knowledge_service.__dict__,
                    "add_knowledge_upload_cleanup",
                    fail_cleanup_database,
                )
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    failed_intent = await client.post(
                        "/api/v1/knowledge-sources",
                        data={
                            "sourceType": "text",
                            "name": "Intent fail",
                            "accessScope": "customer",
                        },
                        files={"file": ("intent.txt", b"safe", "text/plain")},
                    )
                    assert failed_intent.status_code == 500
            assert registration_storage.objects == {}
            assert registration_storage.deleted == []
        finally:
            _clear_overrides()
            if seeded:
                async with session_factory() as session, session.begin():
                    await session.execute(
                        text("DELETE FROM knowledge_upload_cleanups WHERE tenant_id IN (:a, :b)"),
                        {"a": fixture.tenant_a, "b": fixture.tenant_b},
                    )
                    await session.execute(
                        text("DELETE FROM knowledge_sources WHERE tenant_id IN (:a, :b)"),
                        {"a": fixture.tenant_a, "b": fixture.tenant_b},
                    )
                    await cleanup_tenant_isolation_fixture(session, fixture)
            await engine.dispose()

    asyncio.run(scenario())
