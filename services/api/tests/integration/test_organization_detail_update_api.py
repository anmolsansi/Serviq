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
from app.core.principal import require_workforce_user_id
from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)


def _install_overrides(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: UUID | None,
) -> None:
    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_database_session] = override_session
    if user_id is None:
        app.dependency_overrides.pop(require_workforce_user_id, None)
    else:
        app.dependency_overrides[require_workforce_user_id] = lambda: user_id


def _clear_overrides() -> None:
    app.dependency_overrides.pop(get_database_session, None)
    app.dependency_overrides.pop(require_workforce_user_id, None)


async def _seed_matrix(session: AsyncSession, ids: dict[str, UUID]) -> None:
    await session.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, status, default_locale)
            VALUES (:tenant_a, :slug_a, 'Tenant A', 'active', 'en'),
                   (:tenant_b, :slug_b, 'Tenant B', 'active', 'en')
            """
        ),
        {
            "tenant_a": ids["tenant_a"],
            "tenant_b": ids["tenant_b"],
            "slug_a": f"ope284-a-{ids['tenant_a'].hex[:10]}",
            "slug_b": f"ope284-b-{ids['tenant_b'].hex[:10]}",
        },
    )
    for key in ("owner", "admin", "support", "foreign"):
        user_id = ids[key]
        await session.execute(
            text(
                """
                INSERT INTO users (id, oidc_issuer, oidc_subject, email, display_name, status)
                VALUES (:id, 'https://ope284.test', :subject, :email, :name, 'active')
                """
            ),
            {
                "id": user_id,
                "subject": f"{key}-{user_id.hex}",
                "email": f"{key}-{user_id.hex}@example.com",
                "name": key.title(),
            },
        )
    await session.execute(
        text(
            """
            INSERT INTO memberships (id, tenant_id, user_id, status)
            VALUES (:m_owner, :tenant_a, :owner, 'active'),
                   (:m_admin, :tenant_a, :admin, 'active'),
                   (:m_support, :tenant_a, :support, 'active'),
                   (:m_foreign, :tenant_b, :foreign, 'active')
            """
        ),
        ids,
    )
    await session.execute(
        text(
            """
            INSERT INTO roles (id, tenant_id, key, display_name, is_system)
            VALUES (:support_role, :tenant_a, :support_key, 'Support Agent', false)
            """
        ),
        {**ids, "support_key": f"support-{ids['support_role'].hex}"},
    )
    await session.execute(
        text(
            """
            INSERT INTO membership_roles (membership_id, role_id)
            SELECT :m_owner, id FROM roles
            WHERE tenant_id IS NULL AND is_system = true AND key = 'owner'
            UNION ALL
            SELECT :m_admin, id FROM roles
            WHERE tenant_id IS NULL AND is_system = true AND key = 'admin'
            UNION ALL
            SELECT :m_support, :support_role
            """
        ),
        ids,
    )


async def _cleanup_matrix(session: AsyncSession, ids: dict[str, UUID]) -> None:
    await session.execute(
        text(
            """
            DELETE FROM membership_roles
            WHERE membership_id IN (:m_owner, :m_admin, :m_support, :m_foreign)
            """
        ),
        ids,
    )
    await session.execute(
        text("DELETE FROM roles WHERE id = :support_role"),
        ids,
    )
    await session.execute(
        text(
            """
            DELETE FROM memberships
            WHERE id IN (:m_owner, :m_admin, :m_support, :m_foreign)
            """
        ),
        ids,
    )
    for key in ("owner", "admin", "support", "foreign"):
        await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": ids[key]})
    await session.execute(
        text("DELETE FROM tenants WHERE id IN (:tenant_a, :tenant_b)"),
        ids,
    )


def _ids() -> dict[str, UUID]:
    return {
        key: uuid4()
        for key in (
            "tenant_a",
            "tenant_b",
            "owner",
            "admin",
            "support",
            "foreign",
            "m_owner",
            "m_admin",
            "m_support",
            "m_foreign",
            "support_role",
        )
    }


def test_organization_detail_update_authorization_matrix() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        ids = _ids()
        transport = httpx.ASGITransport(app=app)
        try:
            async with session_factory() as session, session.begin():
                await _seed_matrix(session, ids)

            _install_overrides(session_factory, ids["support"])
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                detail = await client.get(f"/api/v1/organizations/{ids['tenant_a']}")
                assert detail.status_code == 200
                assert detail.json()["data"]["displayName"] == "Tenant A"
                denied = await client.patch(
                    f"/api/v1/organizations/{ids['tenant_a']}",
                    json={"displayName": "Support Cannot Edit"},
                )
                assert denied.status_code == 403
                assert denied.json()["error"]["code"] == "FORBIDDEN"

            _install_overrides(session_factory, ids["owner"])
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                owner_update = await client.patch(
                    f"/api/v1/organizations/{ids['tenant_a']}",
                    json={"displayName": " Owner Updated ", "defaultLocale": "en"},
                )
                assert owner_update.status_code == 200
                assert owner_update.json()["data"]["displayName"] == "Owner Updated"

            _install_overrides(session_factory, ids["admin"])
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                admin_update = await client.patch(
                    f"/api/v1/organizations/{ids['tenant_a']}",
                    json={"displayName": "Admin Updated"},
                )
                assert admin_update.status_code == 200
                data = admin_update.json()["data"]
                assert data["displayName"] == "Admin Updated"
                assert data["slug"].startswith("ope284-a-")
                assert data["status"] == "active"
                assert data["defaultLocale"] == "en"

            _install_overrides(session_factory, ids["foreign"])
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                foreign_get = await client.get(f"/api/v1/organizations/{ids['tenant_a']}")
                foreign_patch = await client.patch(
                    f"/api/v1/organizations/{ids['tenant_a']}",
                    json={"displayName": "Foreign Attempt"},
                )
                assert foreign_get.status_code == 404
                assert foreign_patch.status_code == 404
                assert foreign_get.json()["error"]["code"] == "ORGANIZATION_NOT_FOUND"
                assert foreign_patch.json()["error"]["code"] == "ORGANIZATION_NOT_FOUND"
        finally:
            _clear_overrides()
            async with session_factory() as session, session.begin():
                await _cleanup_matrix(session, ids)
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"displayName": "   "},
        {"displayName": "x" * 121},
        {"defaultLocale": "es"},
        {"slug": "immutable"},
        {"status": "suspended"},
    ],
)
def test_organization_patch_rejects_unsafe_or_invalid_fields(body: dict[str, object]) -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        ids = _ids()
        try:
            async with session_factory() as session, session.begin():
                await _seed_matrix(session, ids)
            _install_overrides(session_factory, ids["owner"])
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.patch(
                    f"/api/v1/organizations/{ids['tenant_a']}",
                    json=body,
                )
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        finally:
            _clear_overrides()
            async with session_factory() as session, session.begin():
                await _cleanup_matrix(session, ids)
            await engine.dispose()

    asyncio.run(scenario())


def test_organization_detail_rejects_missing_principal() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        try:
            _install_overrides(session_factory, None)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(f"/api/v1/organizations/{uuid4()}")
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "UNAUTHENTICATED"
        finally:
            _clear_overrides()
            await engine.dispose()

    asyncio.run(scenario())
