from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Mapping
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
        self.put_calls = 0

    def put_object(
        self,
        key: ObjectStorageKey,
        data: bytes | IO[bytes],
        *,
        content_type: str,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        self.put_calls += 1
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


async def _cleanup_row_for_key(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    object_key: str,
) -> Any:
    return (
        await session.execute(
            text(
                "SELECT id, source_id, object_id, object_key, status, attempt_count, "
                "next_attempt_at, last_error_code, resolved_at "
                "FROM knowledge_upload_cleanups "
                "WHERE tenant_id=:tenant AND object_key=:object_key"
            ),
            {"tenant": tenant_id, "object_key": object_key},
        )
    ).one()


def test_file_upload_storage_persistence_permissions_and_consistency(
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

            assert storage.put_calls == 1
            assert len(storage.objects) == 1
            key = next(iter(storage.objects))
            assert key.startswith(f"tenants/{fixture.tenant_a}/knowledge/")
            assert "/raw/" in key
            assert "help.txt" not in key
            assert storage.metadata[key]["original-filename"] == "help.txt"

            async with session_factory() as session:
                row = (
                    await session.execute(
                        text(
                            "SELECT object_key, source_uri, status, sync_version, last_error_code "
                            "FROM knowledge_sources WHERE id=:id AND tenant_id=:tenant"
                        ),
                        {"id": UUID(data["id"]), "tenant": fixture.tenant_a},
                    )
                ).one()
                assert row.object_key == key
                assert row.source_uri is None
                assert row.status == "pending"
                assert row.sync_version == 0
                assert row.last_error_code is None
                cleanup = await _cleanup_row_for_key(
                    session,
                    tenant_id=fixture.tenant_a,
                    object_key=key,
                )
                assert cleanup.source_id == UUID(data["id"])
                assert cleanup.status == "referenced"
                assert cleanup.attempt_count == 0
                assert cleanup.next_attempt_at is None
                assert cleanup.resolved_at is not None

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
            async with session_factory() as session:
                denied_count = (
                    await session.execute(
                        text(
                            "SELECT count(*) FROM knowledge_sources "
                            "WHERE tenant_id=:tenant AND name='Denied'"
                        ),
                        {"tenant": fixture.tenant_a},
                    )
                ).scalar_one()
                assert denied_count == 0

            object_count_before_foreign_attempt = len(storage.objects)
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
            assert len(storage.objects) == object_count_before_foreign_attempt

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
                failed_source_count = (
                    await session.execute(
                        text(
                            "SELECT count(*) FROM knowledge_sources "
                            "WHERE tenant_id=:tenant AND name='Storage fail'"
                        ),
                        {"tenant": fixture.tenant_a},
                    )
                ).scalar_one()
                assert failed_source_count == 0
                cleanup = await _cleanup_row_for_key(
                    session,
                    tenant_id=fixture.tenant_a,
                    object_key=failing_storage.deleted[0],
                )
                assert cleanup.status == "prepared"
                assert cleanup.attempt_count == 0
                assert cleanup.next_attempt_at is not None
                assert cleanup.resolved_at is None

            ambiguous_storage = FakeStorage(fail_after_put=True)
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
            assert ambiguous_storage.objects == {}
            assert len(ambiguous_storage.deleted) == 1
            async with session_factory() as session:
                ambiguous_source_count = (
                    await session.execute(
                        text(
                            "SELECT count(*) FROM knowledge_sources "
                            "WHERE tenant_id=:tenant AND name='Ambiguous storage outcome'"
                        ),
                        {"tenant": fixture.tenant_a},
                    )
                ).scalar_one()
                assert ambiguous_source_count == 0
                cleanup = await _cleanup_row_for_key(
                    session,
                    tenant_id=fixture.tenant_a,
                    object_key=ambiguous_storage.deleted[0],
                )
                assert cleanup.status == "prepared"
                assert cleanup.attempt_count == 0
                assert cleanup.next_attempt_at is not None
                assert cleanup.resolved_at is None

            no_put_storage = FakeStorage()
            monkeypatch.setattr(
                knowledge_router,
                "get_knowledge_object_storage",
                lambda: no_put_storage,
            )

            def fail_cleanup_intent(*args: Any, **kwargs: Any) -> Any:
                raise RuntimeError("synthetic cleanup intent database failure")

            with monkeypatch.context() as intent_patch:
                intent_patch.setitem(
                    knowledge_service.__dict__,
                    "add_upload_cleanup_intent",
                    fail_cleanup_intent,
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
            assert no_put_storage.put_calls == 0
            assert no_put_storage.objects == {}

            db_failure_storage = FakeStorage()
            monkeypatch.setattr(
                knowledge_router,
                "get_knowledge_object_storage",
                lambda: db_failure_storage,
            )

            def fail_source_insert(*args: Any, **kwargs: Any) -> Any:
                raise RuntimeError("synthetic source database failure")

            with monkeypatch.context() as source_patch:
                source_patch.setitem(
                    knowledge_service.__dict__,
                    "add_file_knowledge_source",
                    fail_source_insert,
                )
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    failed_db = await client.post(
                        "/api/v1/knowledge-sources",
                        data={
                            "sourceType": "text",
                            "name": "DB registration fail",
                            "accessScope": "customer",
                        },
                        files={"file": ("db.txt", b"safe", "text/plain")},
                    )
                    assert failed_db.status_code == 500
            assert db_failure_storage.objects == {}
            assert len(db_failure_storage.deleted) == 1
            async with session_factory() as session:
                db_source_count = (
                    await session.execute(
                        text(
                            "SELECT count(*) FROM knowledge_sources "
                            "WHERE tenant_id=:tenant AND name='DB registration fail'"
                        ),
                        {"tenant": fixture.tenant_a},
                    )
                ).scalar_one()
                assert db_source_count == 0
                cleanup = await _cleanup_row_for_key(
                    session,
                    tenant_id=fixture.tenant_a,
                    object_key=db_failure_storage.deleted[0],
                )
                assert cleanup.status == "succeeded"

            double_failure_storage = FakeStorage(fail_delete=True)
            monkeypatch.setattr(
                knowledge_router,
                "get_knowledge_object_storage",
                lambda: double_failure_storage,
            )
            with monkeypatch.context() as source_patch:
                source_patch.setitem(
                    knowledge_service.__dict__,
                    "add_file_knowledge_source",
                    fail_source_insert,
                )
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    double_failed = await client.post(
                        "/api/v1/knowledge-sources",
                        data={
                            "sourceType": "text",
                            "name": "Double failure",
                            "accessScope": "customer",
                        },
                        files={"file": ("double.txt", b"safe", "text/plain")},
                    )
                    assert double_failed.status_code == 500
            assert len(double_failure_storage.objects) == 1
            double_key = next(iter(double_failure_storage.objects))
            assert double_failure_storage.deleted == [double_key]
            async with session_factory() as session:
                double_source_count = (
                    await session.execute(
                        text(
                            "SELECT count(*) FROM knowledge_sources "
                            "WHERE tenant_id=:tenant AND name='Double failure'"
                        ),
                        {"tenant": fixture.tenant_a},
                    )
                ).scalar_one()
                assert double_source_count == 0
                cleanup = await _cleanup_row_for_key(
                    session,
                    tenant_id=fixture.tenant_a,
                    object_key=double_key,
                )
                assert cleanup.status == "pending"
                assert cleanup.attempt_count == 0
                assert cleanup.next_attempt_at is not None
                assert cleanup.resolved_at is None

            prepared_failure_storage = FakeStorage(fail_delete=True)
            monkeypatch.setattr(
                knowledge_router,
                "get_knowledge_object_storage",
                lambda: prepared_failure_storage,
            )

            async def fail_arm(*args: Any, **kwargs: Any) -> None:
                raise RuntimeError("synthetic retry-arm database failure")

            with monkeypatch.context() as prepared_patch:
                prepared_patch.setitem(
                    knowledge_service.__dict__,
                    "add_file_knowledge_source",
                    fail_source_insert,
                )
                prepared_patch.setitem(
                    knowledge_service.__dict__,
                    "arm_upload_cleanup",
                    fail_arm,
                )
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    prepared_failed = await client.post(
                        "/api/v1/knowledge-sources",
                        data={
                            "sourceType": "text",
                            "name": "Prepared fallback",
                            "accessScope": "customer",
                        },
                        files={"file": ("prepared.txt", b"safe", "text/plain")},
                    )
                    assert prepared_failed.status_code == 500
            prepared_key = next(iter(prepared_failure_storage.objects))
            async with session_factory() as session:
                cleanup = await _cleanup_row_for_key(
                    session,
                    tenant_id=fixture.tenant_a,
                    object_key=prepared_key,
                )
                assert cleanup.status == "prepared"
                assert cleanup.attempt_count == 0
                assert cleanup.next_attempt_at is not None
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
