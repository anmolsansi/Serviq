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

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)

KNOWLEDGE_PERMISSION = "knowledge.sources.manage"


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


async def _global_role_id(session: AsyncSession, key: str) -> UUID:
    role_id = await session.scalar(
        text(
            """
            SELECT id FROM roles
            WHERE tenant_id IS NULL AND is_system=true AND key=:key
            """
        ),
        {"key": key},
    )
    assert isinstance(role_id, UUID)
    return role_id


async def _seed(session: AsyncSession) -> dict[str, UUID]:
    ids = {
        name: uuid4()
        for name in (
            "tenant_a",
            "tenant_b",
            "manager",
            "ordinary",
            "foreign",
            "manager_role",
            "ordinary_role",
            "manager_membership",
            "ordinary_membership",
            "foreign_membership",
            "foreign_source",
        )
    }
    owner_role = await _global_role_id(session, "owner")

    await session.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, status, default_locale)
            VALUES (:tenant_a, :slug_a, 'Knowledge A', 'active', 'en'),
                   (:tenant_b, :slug_b, 'Knowledge B', 'active', 'en')
            """
        ),
        {
            **ids,
            "slug_a": f"knowledge-api-a-{ids['tenant_a'].hex[:10]}",
            "slug_b": f"knowledge-api-b-{ids['tenant_b'].hex[:10]}",
        },
    )
    for key in ("manager", "ordinary", "foreign"):
        await session.execute(
            text(
                """
                INSERT INTO users (
                  id, oidc_issuer, oidc_subject, email, display_name, status
                ) VALUES (
                  :id, 'https://ope302.test', :subject, :email, :name, 'active'
                )
                """
            ),
            {
                "id": ids[key],
                "subject": f"{key}-{ids[key].hex}",
                "email": f"{key}@example.com",
                "name": key.title(),
            },
        )

    await session.execute(
        text(
            """
            INSERT INTO roles (id, tenant_id, key, display_name, is_system)
            VALUES (:manager_role, :tenant_a, :manager_key, 'Knowledge Manager', false),
                   (:ordinary_role, :tenant_a, :ordinary_key, 'Ordinary Agent', false)
            """
        ),
        {
            **ids,
            "manager_key": f"knowledge-manager-{ids['manager_role'].hex}",
            "ordinary_key": f"ordinary-{ids['ordinary_role'].hex}",
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO role_permissions (role_id, permission_key)
            VALUES (:manager_role, :permission)
            """
        ),
        {"manager_role": ids["manager_role"], "permission": KNOWLEDGE_PERMISSION},
    )
    await session.execute(
        text(
            """
            INSERT INTO memberships (id, tenant_id, user_id, status)
            VALUES (:manager_membership, :tenant_a, :manager, 'active'),
                   (:ordinary_membership, :tenant_a, :ordinary, 'active'),
                   (:foreign_membership, :tenant_b, :foreign, 'active')
            """
        ),
        ids,
    )
    await session.execute(
        text(
            """
            INSERT INTO membership_roles (membership_id, role_id)
            VALUES (:manager_membership, :manager_role),
                   (:ordinary_membership, :ordinary_role),
                   (:foreign_membership, :owner_role)
            """
        ),
        {**ids, "owner_role": owner_role},
    )
    await session.execute(
        text(
            """
            INSERT INTO knowledge_sources (
              id, tenant_id, source_type, name, source_uri, access_scope,
              status, sync_version, created_by
            ) VALUES (
              :foreign_source, :tenant_b, 'url', 'Foreign source',
              'https://foreign.example.com/docs', 'customer', 'ready', 4, :foreign
            )
            """
        ),
        ids,
    )
    return ids


async def _cleanup(session: AsyncSession, ids: dict[str, UUID]) -> None:
    await session.execute(
        text("DELETE FROM knowledge_sources WHERE tenant_id IN (:a, :b)"),
        {"a": ids["tenant_a"], "b": ids["tenant_b"]},
    )
    await session.execute(
        text(
            """
            DELETE FROM membership_roles WHERE membership_id IN (
              :manager_membership, :ordinary_membership, :foreign_membership
            )
            """
        ),
        ids,
    )
    await session.execute(
        text(
            """
            DELETE FROM memberships WHERE id IN (
              :manager_membership, :ordinary_membership, :foreign_membership
            )
            """
        ),
        ids,
    )
    await session.execute(
        text("DELETE FROM role_permissions WHERE role_id=:role"),
        {"role": ids["manager_role"]},
    )
    await session.execute(
        text("DELETE FROM roles WHERE id IN (:manager_role, :ordinary_role)"),
        ids,
    )
    await session.execute(
        text("DELETE FROM users WHERE id IN (:manager, :ordinary, :foreign)"),
        ids,
    )
    await session.execute(
        text("DELETE FROM tenants WHERE id IN (:a, :b)"),
        {"a": ids["tenant_a"], "b": ids["tenant_b"]},
    )


def test_knowledge_source_create_list_validation_and_tenant_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        transport = httpx.ASGITransport(app=app)
        ids: dict[str, UUID] = {}
        try:
            async with session_factory() as session, session.begin():
                ids = await _seed(session)

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
                user_id=ids["manager"],
                tenant_id=ids["tenant_a"],
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
                listed_ids = {UUID(item["id"]) for item in listed.json()["data"]}
                assert listed_ids == {url_id, sitemap_id}
                assert ids["foreign_source"] not in listed_ids

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
                        {"id": url_id, "tenant": ids["tenant_a"]},
                    )
                ).one()
                assert persisted.status == "pending"
                assert persisted.sync_version == 0
                assert persisted.object_key is None

            _install_overrides(
                session_factory,
                user_id=ids["ordinary"],
                tenant_id=ids["tenant_a"],
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
            if ids:
                async with session_factory() as session, session.begin():
                    await _cleanup(session, ids)
            await engine.dispose()

    asyncio.run(scenario())
