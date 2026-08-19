from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
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
from app.core.principal import require_tenant_id, require_workforce_user_id
from app.main import app
from tests.support.tenant_isolation import (
    TenantIsolationFixture,
    assert_list_excludes_foreign,
    cleanup_tenant_isolation_fixture,
    seed_tenant_isolation_fixture,
)

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)


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
    for dependency in (
        get_database_session,
        require_workforce_user_id,
        require_tenant_id,
    ):
        app.dependency_overrides.pop(dependency, None)


async def _seed_foreign_source(
    session: AsyncSession,
    *,
    fixture: TenantIsolationFixture,
    source_id: UUID,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO knowledge_sources (
              id, tenant_id, source_type, name, source_uri, access_scope,
              status, sync_version, created_by
            ) VALUES (
              :source_id, :tenant_id, 'url', 'Shared Knowledge',
              'https://foreign.example.com/docs', 'customer', 'ready', 4, :created_by
            )
            """
        ),
        {
            "source_id": source_id,
            "tenant_id": fixture.tenant_b,
            "created_by": fixture.owner_b,
        },
    )


async def _cleanup_knowledge_sources(
    session: AsyncSession,
    *,
    fixture: TenantIsolationFixture,
) -> None:
    await session.execute(
        text("DELETE FROM knowledge_sources WHERE tenant_id IN (:a, :b)"),
        {"a": fixture.tenant_a, "b": fixture.tenant_b},
    )


def test_knowledge_source_create_list_validation_and_tenant_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        fixture = TenantIsolationFixture.new()
        foreign_source_id = uuid4()
        transport = httpx.ASGITransport(app=app)
        seeded = False
        try:
            async with session_factory() as session, session.begin():
                await seed_tenant_isolation_fixture(session, fixture)
                await _seed_foreign_source(
                    session,
                    fixture=fixture,
                    source_id=foreign_source_id,
                )
                seeded = True

            async def reject_outbound_http(
                _transport: httpx.AsyncHTTPTransport,
                _request: httpx.Request,
            ) -> httpx.Response:
                raise AssertionError("knowledge source create must not perform outbound HTTP")

            monkeypatch.setattr(
                httpx.AsyncHTTPTransport,
                "handle_async_request",
                reject_outbound_http,
            )

            _install_overrides(
                session_factory,
                user_id=fixture.owner_a,
                tenant_id=fixture.tenant_a,
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                url_created = await client.post(
                    "/api/v1/knowledge-sources",
                    json={
                        "sourceType": "url",
                        "name": "  Public Help  ",
                        "sourceUri": "https://docs.example.com/help",
                        "accessScope": "customer",
                    },
                )
                assert url_created.status_code == 201
                url_data = url_created.json()["data"]
                url_id = UUID(url_data["id"])
                assert url_data["name"] == "Public Help"
                assert url_data["status"] == "pending"
                assert url_data["syncVersion"] == 0
                assert url_data["lastSyncedAt"] is None
                assert url_data["lastErrorCode"] is None
                assert "objectKey" not in url_data
                assert "createdBy" not in url_data

                sitemap_created = await client.post(
                    "/api/v1/knowledge-sources",
                    json={
                        "sourceType": "sitemap",
                        "name": "Docs sitemap",
                        "sourceUri": "https://docs.example.com/sitemap.xml",
                        "accessScope": "internal",
                    },
                )
                assert sitemap_created.status_code == 201
                sitemap_id = UUID(sitemap_created.json()["data"]["id"])

                listed = await client.get("/api/v1/knowledge-sources")
                assert listed.status_code == 200
                listed_items = listed.json()["data"]
                listed_ids = {UUID(item["id"]) for item in listed_items}
                assert listed_ids == {url_id, sitemap_id}
                assert_list_excludes_foreign(
                    listed_items,
                    foreign_id=foreign_source_id,
                    id_of=lambda item: UUID(item["id"]),
                )

                invalid_payloads = [
                    {
                        "sourceType": "url",
                        "name": "HTTP",
                        "sourceUri": "http://example.com",
                        "accessScope": "customer",
                    },
                    {
                        "sourceType": "url",
                        "name": "Credentials",
                        "sourceUri": "https://user:pass@example.com/docs",
                        "accessScope": "customer",
                    },
                    {
                        "sourceType": "sitemap",
                        "name": "Fragment",
                        "sourceUri": "https://example.com/sitemap.xml#part",
                        "accessScope": "customer",
                    },
                    {
                        "sourceType": "url",
                        "name": "Scope",
                        "sourceUri": "https://example.com",
                        "accessScope": "public",
                    },
                    {
                        "sourceType": "url",
                        "name": "   ",
                        "sourceUri": "https://example.com",
                        "accessScope": "customer",
                    },
                    {
                        "sourceType": "url",
                        "name": "x" * 161,
                        "sourceUri": "https://example.com",
                        "accessScope": "customer",
                    },
                    {
                        "sourceType": "url",
                        "name": "Unknown field",
                        "sourceUri": "https://example.com",
                        "accessScope": "customer",
                        "crawlNow": True,
                    },
                ]
                for payload in invalid_payloads:
                    invalid = await client.post("/api/v1/knowledge-sources", json=payload)
                    assert invalid.status_code == 422

            async with session_factory() as session:
                persisted = (
                    await session.execute(
                        text(
                            """
                            SELECT status, sync_version, object_key
                            FROM knowledge_sources
                            WHERE id=:id AND tenant_id=:tenant
                            """
                        ),
                        {"id": url_id, "tenant": fixture.tenant_a},
                    )
                ).one()
                assert persisted.status == "pending"
                assert persisted.sync_version == 0
                assert persisted.object_key is None

            _install_overrides(
                session_factory,
                user_id=fixture.member_a,
                tenant_id=fixture.tenant_a,
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                denied_list = await client.get("/api/v1/knowledge-sources")
                assert denied_list.status_code == 403
                denied_create = await client.post(
                    "/api/v1/knowledge-sources",
                    json={
                        "sourceType": "url",
                        "name": "Denied",
                        "sourceUri": "https://example.com/denied",
                        "accessScope": "customer",
                    },
                )
                assert denied_create.status_code == 403
        finally:
            _clear_overrides()
            if seeded:
                async with session_factory() as session, session.begin():
                    await _cleanup_knowledge_sources(session, fixture=fixture)
                    await cleanup_tenant_isolation_fixture(session, fixture)
            await engine.dispose()

    asyncio.run(scenario())
