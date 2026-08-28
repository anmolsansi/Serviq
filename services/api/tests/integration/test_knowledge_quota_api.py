from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import IO, Any
from uuid import UUID, uuid4

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
from app.core.object_storage import ObjectStorageKey
from app.core.principal import require_tenant_id, require_workforce_user_id
from app.core.rate_limits import (
    KnowledgeUploadRateLimitUnavailableError,
    RateLimitDecision,
)
from app.main import app
from app.modules.knowledge import router as knowledge_router
from app.modules.knowledge.router import get_knowledge_upload_rate_limiter_dependency
from tests.support.tenant_isolation import (
    TenantIsolationFixture,
    cleanup_tenant_isolation_fixture,
    seed_tenant_isolation_fixture,
)

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)


class CountingStorage:
    def __init__(self) -> None:
        self.put_calls = 0

    def put_object(
        self,
        key: ObjectStorageKey,
        data: bytes | IO[bytes],
        *,
        content_type: str,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        del key, data, content_type, metadata
        self.put_calls += 1

    def delete_object(self, key: ObjectStorageKey) -> None:
        del key

    def get_object(self, key: ObjectStorageKey) -> Any:
        raise NotImplementedError

    def head(self, key: ObjectStorageKey) -> Any:
        raise NotImplementedError

    def exists(self, key: ObjectStorageKey) -> bool:
        del key
        return False


class FixedUploadLimiter:
    def __init__(
        self,
        decision: RateLimitDecision | None = None,
        *,
        unavailable: bool = False,
    ) -> None:
        self.decision = decision or RateLimitDecision(allowed=True)
        self.unavailable = unavailable
        self.calls = 0

    async def check_and_consume(self, *, tenant_id: UUID, user_id: UUID) -> RateLimitDecision:
        del tenant_id, user_id
        self.calls += 1
        if self.unavailable:
            raise KnowledgeUploadRateLimitUnavailableError
        return self.decision


def _install_overrides(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: UUID,
    tenant_id: UUID,
    limiter: FixedUploadLimiter,
) -> None:
    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_database_session] = override_session
    app.dependency_overrides[require_workforce_user_id] = lambda: user_id
    app.dependency_overrides[require_tenant_id] = lambda: tenant_id
    app.dependency_overrides[get_knowledge_upload_rate_limiter_dependency] = lambda: limiter


async def _delete_knowledge_rows(session: AsyncSession, *, tenant_id: UUID) -> None:
    await session.execute(
        text("DELETE FROM knowledge_upload_reservations WHERE tenant_id=:tenant"),
        {"tenant": tenant_id},
    )
    await session.execute(
        text("DELETE FROM knowledge_upload_cleanups WHERE tenant_id=:tenant"),
        {"tenant": tenant_id},
    )
    await session.execute(
        text("DELETE FROM knowledge_sources WHERE tenant_id=:tenant"),
        {"tenant": tenant_id},
    )


def test_upload_rate_rejection_and_limiter_outage_happen_before_object_put(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        fixture = TenantIsolationFixture.new()
        storage = CountingStorage()
        seeded = False
        try:
            async with session_factory() as session, session.begin():
                await seed_tenant_isolation_fixture(session, fixture)
                seeded = True

            monkeypatch.setattr(knowledge_router, "get_knowledge_object_storage", lambda: storage)
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

            limited = FixedUploadLimiter(RateLimitDecision(allowed=False, retry_after_seconds=23))
            _install_overrides(
                session_factory,
                user_id=fixture.owner_a,
                tenant_id=fixture.tenant_a,
                limiter=limited,
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/knowledge-sources",
                    data={"sourceType": "text", "name": "Rate blocked", "accessScope": "customer"},
                    files={"file": ("blocked.txt", b"blocked", "text/plain")},
                )
            assert response.status_code == 429
            assert response.headers["Retry-After"] == "23"
            assert response.json() == {
                "error": {
                    "code": "KNOWLEDGE_UPLOAD_RATE_LIMITED",
                    "message": "Knowledge upload request rate exceeded.",
                }
            }
            assert limited.calls == 1
            assert storage.put_calls == 0

            unavailable = FixedUploadLimiter(unavailable=True)
            _install_overrides(
                session_factory,
                user_id=fixture.owner_a,
                tenant_id=fixture.tenant_a,
                limiter=unavailable,
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/knowledge-sources",
                    data={"sourceType": "text", "name": "Limiter down", "accessScope": "customer"},
                    files={"file": ("blocked.txt", b"blocked", "text/plain")},
                )
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "KNOWLEDGE_UPLOAD_LIMITER_UNAVAILABLE"
            assert storage.put_calls == 0

            async with session_factory() as session:
                count = (
                    await session.execute(
                        text("SELECT count(*) FROM knowledge_sources WHERE tenant_id=:tenant"),
                        {"tenant": fixture.tenant_a},
                    )
                ).scalar_one()
                assert count == 0
        finally:
            app.dependency_overrides.clear()
            if seeded:
                async with session_factory() as session, session.begin():
                    await _delete_knowledge_rows(session, tenant_id=fixture.tenant_a)
                    await _delete_knowledge_rows(session, tenant_id=fixture.tenant_b)
                    await cleanup_tenant_isolation_fixture(session, fixture)
            await engine.dispose()

    asyncio.run(scenario())


def test_source_and_concurrency_quota_failures_create_no_object_or_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        fixture = TenantIsolationFixture.new()
        storage = CountingStorage()
        limiter = FixedUploadLimiter()
        seeded = False
        try:
            async with session_factory() as session, session.begin():
                await seed_tenant_isolation_fixture(session, fixture)
                seeded = True
                for index in range(100):
                    await session.execute(
                        text(
                            """
                            INSERT INTO knowledge_sources (
                              id, tenant_id, source_type, name, source_uri, object_key,
                              object_size_bytes, access_scope, status, sync_version,
                              last_synced_at, last_error_code, created_by, created_at, updated_at
                            ) VALUES (
                              :id, :tenant, 'url', :name, :uri, NULL, NULL,
                              'customer', 'pending', 0, NULL, NULL, :created_by, now(), now()
                            )
                            """
                        ),
                        {
                            "id": uuid4(),
                            "tenant": fixture.tenant_a,
                            "name": f"source-cap-{index}",
                            "uri": f"https://example.test/source-cap/{index}",
                            "created_by": fixture.owner_a,
                        },
                    )

            monkeypatch.setattr(knowledge_router, "get_knowledge_object_storage", lambda: storage)
            _install_overrides(
                session_factory,
                user_id=fixture.owner_a,
                tenant_id=fixture.tenant_a,
                limiter=limiter,
            )
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/knowledge-sources",
                    data={"sourceType": "text", "name": "Over cap", "accessScope": "customer"},
                    files={"file": ("over.txt", b"no write", "text/plain")},
                )
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "KNOWLEDGE_SOURCE_QUOTA_EXCEEDED"
            assert storage.put_calls == 0

            async with session_factory() as session, session.begin():
                await session.execute(
                    text("DELETE FROM knowledge_sources WHERE tenant_id=:tenant"),
                    {"tenant": fixture.tenant_a},
                )
                now = datetime.now(UTC)
                for _ in range(3):
                    await session.execute(
                        text(
                            """
                            INSERT INTO knowledge_upload_reservations (
                              id, tenant_id, source_id, reserved_bytes, cleanup_id,
                              lease_expires_at, created_at, updated_at
                            ) VALUES (
                              :id, :tenant, :source_id, 1, NULL,
                              :lease_expires_at, :now, :now
                            )
                            """
                        ),
                        {
                            "id": uuid4(),
                            "tenant": fixture.tenant_a,
                            "source_id": uuid4(),
                            "lease_expires_at": now + timedelta(minutes=5),
                            "now": now,
                        },
                    )

            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/knowledge-sources",
                    data={"sourceType": "text", "name": "Concurrent", "accessScope": "customer"},
                    files={"file": ("concurrent.txt", b"no write", "text/plain")},
                )
            assert response.status_code == 429
            assert response.json()["error"]["code"] == "KNOWLEDGE_UPLOAD_CONCURRENCY_LIMITED"
            assert int(response.headers["Retry-After"]) >= 1
            assert storage.put_calls == 0
        finally:
            app.dependency_overrides.clear()
            if seeded:
                async with session_factory() as session, session.begin():
                    await _delete_knowledge_rows(session, tenant_id=fixture.tenant_a)
                    await _delete_knowledge_rows(session, tenant_id=fixture.tenant_b)
                    await cleanup_tenant_isolation_fixture(session, fixture)
            await engine.dispose()

    asyncio.run(scenario())
