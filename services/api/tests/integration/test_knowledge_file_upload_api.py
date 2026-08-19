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
    def __init__(self, *, fail_put: bool = False) -> None:
        self.fail_put = fail_put
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

    def delete_object(self, key: ObjectStorageKey) -> None:
        self.deleted.append(key.value)
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


def test_file_upload_storage_persistence_permissions_and_compensation(
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
                assert "objectKey" not in data
                assert "createdBy" not in data

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
                            "SELECT object_key, source_uri, status, sync_version "
                            "FROM knowledge_sources WHERE id=:id AND tenant_id=:tenant"
                        ),
                        {"id": UUID(data["id"]), "tenant": fixture.tenant_a},
                    )
                ).one()
                assert row.object_key == key
                assert row.source_uri is None
                assert row.status == "pending"
                assert row.sync_version == 0

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

            compensation_storage = FakeStorage()
            monkeypatch.setattr(
                knowledge_router,
                "get_knowledge_object_storage",
                lambda: compensation_storage,
            )

            def fail_database(*args: Any, **kwargs: Any) -> Any:
                raise RuntimeError("synthetic database failure")

            monkeypatch.setitem(
                knowledge_service.__dict__,
                "add_file_knowledge_source",
                fail_database,
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                failed_db = await client.post(
                    "/api/v1/knowledge-sources",
                    data={"sourceType": "text", "name": "DB fail", "accessScope": "customer"},
                    files={"file": ("db.txt", b"safe", "text/plain")},
                )
                assert failed_db.status_code == 500
            assert compensation_storage.objects == {}
            assert len(compensation_storage.deleted) == 1
        finally:
            _clear_overrides()
            if seeded:
                async with session_factory() as session, session.begin():
                    await session.execute(
                        text("DELETE FROM knowledge_sources WHERE tenant_id IN (:a, :b)"),
                        {"a": fixture.tenant_a, "b": fixture.tenant_b},
                    )
                    await cleanup_tenant_isolation_fixture(session, fixture)
            await engine.dispose()

    asyncio.run(scenario())
