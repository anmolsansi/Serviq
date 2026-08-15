from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import load_settings
from app.core.database import (
    create_database_engine,
    create_database_session_factory,
    get_database_session,
)
from app.core.principal import require_workforce_user_id
from app.main import app
from app.modules.invitations.models import OrganizationInvitation
from app.modules.invitations.security import hash_invitation_token
from app.modules.tenancy.models import Role

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


async def _seed_invitation_matrix(session: AsyncSession, ids: dict[str, UUID]) -> None:
    await session.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, status, default_locale)
            VALUES (:tenant_a, :slug_a, 'Invitation Tenant A', 'active', 'en'),
                   (:tenant_b, :slug_b, 'Invitation Tenant B', 'active', 'en')
            """
        ),
        {
            "tenant_a": ids["tenant_a"],
            "tenant_b": ids["tenant_b"],
            "slug_a": f"ope285-a-{ids['tenant_a'].hex[:10]}",
            "slug_b": f"ope285-b-{ids['tenant_b'].hex[:10]}",
        },
    )

    for key in ("owner", "admin", "support", "foreign"):
        user_id = ids[key]
        await session.execute(
            text(
                """
                INSERT INTO users (id, oidc_issuer, oidc_subject, email, display_name, status)
                VALUES (:id, 'https://ope285.test', :subject, :email, :name, 'active')
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
            VALUES (:tenant_role_a, :tenant_a, :tenant_role_a_key, 'Tenant A Agent', false),
                   (:tenant_role_b, :tenant_b, :tenant_role_b_key, 'Tenant B Agent', false),
                   (:support_role, :tenant_a, :support_role_key, 'Support Only', false),
                   (:platform_role, NULL, :platform_role_key, 'Platform Internal', true)
            """
        ),
        {
            **ids,
            "tenant_role_a_key": f"agent-a-{ids['tenant_role_a'].hex}",
            "tenant_role_b_key": f"agent-b-{ids['tenant_role_b'].hex}",
            "support_role_key": f"support-{ids['support_role'].hex}",
            "platform_role_key": f"platform-internal-{ids['platform_role'].hex}",
        },
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
            UNION ALL
            SELECT :m_foreign, id FROM roles
            WHERE tenant_id IS NULL AND is_system = true AND key = 'owner'
            """
        ),
        ids,
    )


async def _cleanup_invitation_matrix(session: AsyncSession, ids: dict[str, UUID]) -> None:
    await session.execute(
        text(
            """
            DELETE FROM organization_invitation_roles
            WHERE invitation_id IN (
                SELECT id FROM organization_invitations
                WHERE tenant_id IN (:tenant_a, :tenant_b)
            )
            """
        ),
        ids,
    )
    await session.execute(
        text(
            """
            DELETE FROM organization_invitations
            WHERE tenant_id IN (:tenant_a, :tenant_b)
            """
        ),
        ids,
    )
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
        text(
            """
            DELETE FROM roles
            WHERE id IN (:tenant_role_a, :tenant_role_b, :support_role, :platform_role)
            """
        ),
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
            "tenant_role_a",
            "tenant_role_b",
            "support_role",
            "platform_role",
        )
    }


async def _insert_accepted_invitation(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
    invitation_id: UUID,
) -> None:
    now = datetime.now(UTC)
    await session.execute(
        text(
            """
            INSERT INTO organization_invitations (
                id, tenant_id, email_normalized, token_hash, status,
                invited_by_user_id, accepted_by_user_id, expires_at, accepted_at
            )
            VALUES (
                :id, :tenant_id, :email, :token_hash, 'accepted',
                :user_id, :user_id, :expires_at, :accepted_at
            )
            """
        ),
        {
            "id": invitation_id,
            "tenant_id": tenant_id,
            "email": f"accepted-{invitation_id.hex}@example.com",
            "token_hash": "a" * 64,
            "user_id": user_id,
            "expires_at": now + timedelta(days=7),
            "accepted_at": now,
        },
    )


def test_invitation_create_list_revoke_security_matrix(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        ids = _ids()
        transport = httpx.ASGITransport(app=app)
        try:
            async with session_factory() as session, session.begin():
                await _seed_invitation_matrix(session, ids)

            async with session_factory() as session:
                owner_role_id = await session.scalar(
                    select(Role.id).where(
                        Role.tenant_id.is_(None),
                        Role.is_system.is_(True),
                        Role.key == "owner",
                    )
                )
                admin_role_id = await session.scalar(
                    select(Role.id).where(
                        Role.tenant_id.is_(None),
                        Role.is_system.is_(True),
                        Role.key == "admin",
                    )
                )
            assert owner_role_id is not None
            assert admin_role_id is not None

            _install_overrides(session_factory, ids["owner"])
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                created = await client.post(
                    f"/api/v1/organizations/{ids['tenant_a']}/invitations",
                    json={
                        "email": " Invitee@Example.COM ",
                        "roleIds": [str(ids["tenant_role_a"]), str(admin_role_id)],
                    },
                )
                assert created.status_code == 201
                created_data = created.json()["data"]
                assert created_data["email"] == "invitee@example.com"
                assert created_data["status"] == "pending"
                assert {role["id"] for role in created_data["roles"]} == {
                    str(ids["tenant_role_a"]),
                    str(admin_role_id),
                }

                invite_url = created_data["inviteUrl"]
                token_values = parse_qs(urlsplit(invite_url).query).get("token", [])
                assert len(token_values) == 1
                plaintext_token = token_values[0]
                assert plaintext_token
                assert invite_url.count(plaintext_token) == 1
                token_hash = hash_invitation_token(plaintext_token)

                duplicate = await client.post(
                    f"/api/v1/organizations/{ids['tenant_a']}/invitations",
                    json={
                        "email": "invitee@example.com",
                        "roleIds": [str(ids["tenant_role_a"])],
                    },
                )
                assert duplicate.status_code == 409
                assert duplicate.json()["error"]["code"] == "INVITATION_CONFLICT"

                foreign_role = await client.post(
                    f"/api/v1/organizations/{ids['tenant_a']}/invitations",
                    json={
                        "email": "foreign-role@example.com",
                        "roleIds": [str(ids["tenant_role_b"])],
                    },
                )
                assert foreign_role.status_code == 422
                assert foreign_role.json()["error"]["code"] == "INVITATION_ROLE_INVALID"

                platform_role = await client.post(
                    f"/api/v1/organizations/{ids['tenant_a']}/invitations",
                    json={
                        "email": "platform-role@example.com",
                        "roleIds": [str(ids["platform_role"])],
                    },
                )
                assert platform_role.status_code == 422
                assert platform_role.json()["error"]["code"] == "INVITATION_ROLE_INVALID"

                listed = await client.get(
                    f"/api/v1/organizations/{ids['tenant_a']}/invitations"
                )
                assert listed.status_code == 200
                listed_text = listed.text
                assert plaintext_token not in listed_text
                assert token_hash not in listed_text
                assert "token_hash" not in listed_text
                assert "inviteUrl" not in listed_text

            created_id = UUID(created_data["id"])
            async with session_factory() as session:
                stored = await session.scalar(
                    select(OrganizationInvitation).where(OrganizationInvitation.id == created_id)
                )
                assert stored is not None
                assert stored.email_normalized == "invitee@example.com"
                assert stored.token_hash == token_hash
                assert plaintext_token != stored.token_hash
                delta = stored.expires_at - stored.created_at
                assert timedelta(days=6, hours=23, minutes=59) < delta < timedelta(
                    days=7, minutes=1
                )

            assert plaintext_token not in caplog.text
            assert token_hash not in caplog.text

            _install_overrides(session_factory, ids["admin"])
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                admin_create = await client.post(
                    f"/api/v1/organizations/{ids['tenant_a']}/invitations",
                    json={
                        "email": "admin-created@example.com",
                        "roleIds": [str(owner_role_id)],
                    },
                )
                assert admin_create.status_code == 201

            _install_overrides(session_factory, ids["support"])
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                denied = await client.post(
                    f"/api/v1/organizations/{ids['tenant_a']}/invitations",
                    json={
                        "email": "denied@example.com",
                        "roleIds": [str(ids["tenant_role_a"])],
                    },
                )
                assert denied.status_code == 403
                assert denied.json()["error"]["code"] == "FORBIDDEN"

            _install_overrides(session_factory, ids["foreign"])
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                foreign_list = await client.get(
                    f"/api/v1/organizations/{ids['tenant_a']}/invitations"
                )
                foreign_revoke = await client.delete(
                    f"/api/v1/organizations/{ids['tenant_a']}/invitations/{created_id}"
                )
                assert foreign_list.status_code == 404
                assert foreign_revoke.status_code == 404

            _install_overrides(session_factory, ids["owner"])
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                revoked = await client.delete(
                    f"/api/v1/organizations/{ids['tenant_a']}/invitations/{created_id}"
                )
                assert revoked.status_code == 200
                assert revoked.json()["data"]["status"] == "revoked"
                assert revoked.json()["data"]["revokedAt"] is not None
                assert "inviteUrl" not in revoked.text
                assert plaintext_token not in revoked.text
                assert token_hash not in revoked.text

                repeated_revoke = await client.delete(
                    f"/api/v1/organizations/{ids['tenant_a']}/invitations/{created_id}"
                )
                assert repeated_revoke.status_code == 409
                assert (
                    repeated_revoke.json()["error"]["code"]
                    == "INVITATION_LIFECYCLE_CONFLICT"
                )

                accepted_id = uuid4()
                async with session_factory() as session, session.begin():
                    await _insert_accepted_invitation(
                        session,
                        tenant_id=ids["tenant_a"],
                        user_id=ids["owner"],
                        invitation_id=accepted_id,
                    )

                accepted_revoke = await client.delete(
                    f"/api/v1/organizations/{ids['tenant_a']}/invitations/{accepted_id}"
                )
                assert accepted_revoke.status_code == 409
                assert (
                    accepted_revoke.json()["error"]["code"]
                    == "INVITATION_LIFECYCLE_CONFLICT"
                )
        finally:
            _clear_overrides()
            async with session_factory() as session, session.begin():
                await _cleanup_invitation_matrix(session, ids)
            await engine.dispose()

    asyncio.run(scenario())


def test_invitation_input_validation_and_authentication() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        ids = _ids()
        transport = httpx.ASGITransport(app=app)
        try:
            async with session_factory() as session, session.begin():
                await _seed_invitation_matrix(session, ids)

            _install_overrides(session_factory, ids["owner"])
            invalid_bodies: tuple[dict[str, object], ...] = (
                {"email": "not-an-email", "roleIds": [str(ids["tenant_role_a"])]},
                {"email": "user@example.com", "roleIds": []},
                {
                    "email": "user@example.com",
                    "roleIds": [str(ids["tenant_role_a"]), str(ids["tenant_role_a"])],
                },
                {
                    "email": "user@example.com",
                    "roleIds": [str(ids["tenant_role_a"])],
                    "token": "client-cannot-supply-this",
                },
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                for body in invalid_bodies:
                    response = await client.post(
                        f"/api/v1/organizations/{ids['tenant_a']}/invitations",
                        json=body,
                    )
                    assert response.status_code == 422
                    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

            _install_overrides(session_factory, None)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                unauthenticated = await client.get(
                    f"/api/v1/organizations/{ids['tenant_a']}/invitations"
                )
                assert unauthenticated.status_code == 401
                assert unauthenticated.json()["error"]["code"] == "UNAUTHENTICATED"
        finally:
            _clear_overrides()
            async with session_factory() as session, session.begin():
                await _cleanup_invitation_matrix(session, ids)
            await engine.dispose()

    asyncio.run(scenario())
