from __future__ import annotations

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


def _ids() -> dict[str, UUID]:
    return {
        name: uuid4()
        for name in (
            "tenant_a",
            "tenant_b",
            "owner_a",
            "owner2_a",
            "admin_a",
            "member_a",
            "ordinary_a",
            "member_b",
            "owner_membership_a",
            "owner2_membership_a",
            "admin_membership_a",
            "member_membership_a",
            "ordinary_membership_a",
            "member_membership_b",
            "support_a",
            "qa_a",
            "support_b",
            "platform_role",
        )
    }


def _install_overrides(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: UUID,
) -> None:
    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_database_session] = override_session
    app.dependency_overrides[require_workforce_user_id] = lambda: user_id


def _clear_overrides() -> None:
    app.dependency_overrides.pop(get_database_session, None)
    app.dependency_overrides.pop(require_workforce_user_id, None)


async def _global_role_id(session: AsyncSession, key: str) -> UUID:
    role_id = await session.scalar(
        text(
            """
            SELECT id FROM roles
            WHERE tenant_id IS NULL AND is_system = true AND key = :key
            """
        ),
        {"key": key},
    )
    assert isinstance(role_id, UUID)
    return role_id


async def _seed(session: AsyncSession, ids: dict[str, UUID]) -> tuple[UUID, UUID]:
    owner_role = await _global_role_id(session, "owner")
    admin_role = await _global_role_id(session, "admin")

    await session.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, status, default_locale)
            VALUES (:tenant_a, :slug_a, 'Shared Team Name', 'active', 'en'),
                   (:tenant_b, :slug_b, 'Shared Team Name', 'active', 'en')
            """
        ),
        {
            **ids,
            "slug_a": f"ope287-a-{ids['tenant_a'].hex[:10]}",
            "slug_b": f"ope287-b-{ids['tenant_b'].hex[:10]}",
        },
    )

    for key, email, display_name in (
        ("owner_a", "owner@example.com", "Shared User"),
        ("owner2_a", "owner2@example.com", "Shared User"),
        ("admin_a", "admin@example.com", "Shared Admin"),
        ("member_a", "member@example.com", "Shared Member"),
        ("ordinary_a", "ordinary@example.com", "Shared Member"),
        ("member_b", "member@example.com", "Shared Member"),
    ):
        await session.execute(
            text(
                """
                INSERT INTO users (
                    id, oidc_issuer, oidc_subject, email, display_name, status
                ) VALUES (:id, :issuer, :subject, :email, :display_name, 'active')
                """
            ),
            {
                "id": ids[key],
                "issuer": "https://ope287.test",
                "subject": f"{key}-{ids[key].hex}",
                "email": email,
                "display_name": display_name,
            },
        )

    await session.execute(
        text(
            """
            INSERT INTO roles (id, tenant_id, key, display_name, is_system)
            VALUES
              (:support_a, :tenant_a, :support_key_a, 'Shared Support', false),
              (:qa_a, :tenant_a, :qa_key_a, 'Quality Agent', false),
              (:support_b, :tenant_b, :support_key_b, 'Shared Support', false),
              (:platform_role, NULL, :platform_key, 'Platform Operator Test', true)
            """
        ),
        {
            **ids,
            "support_key_a": f"support-{ids['support_a'].hex}",
            "qa_key_a": f"qa-{ids['qa_a'].hex}",
            "support_key_b": f"support-{ids['support_b'].hex}",
            "platform_key": f"platform-operator-{ids['platform_role'].hex}",
        },
    )

    await session.execute(
        text(
            """
            INSERT INTO memberships (id, tenant_id, user_id, status)
            VALUES
              (:owner_membership_a, :tenant_a, :owner_a, 'active'),
              (:owner2_membership_a, :tenant_a, :owner2_a, 'active'),
              (:admin_membership_a, :tenant_a, :admin_a, 'active'),
              (:member_membership_a, :tenant_a, :member_a, 'active'),
              (:ordinary_membership_a, :tenant_a, :ordinary_a, 'active'),
              (:member_membership_b, :tenant_b, :member_b, 'active')
            """
        ),
        ids,
    )

    await session.execute(
        text(
            """
            INSERT INTO membership_roles (membership_id, role_id)
            VALUES
              (:owner_membership_a, :owner_role),
              (:owner2_membership_a, :owner_role),
              (:admin_membership_a, :admin_role),
              (:member_membership_a, :support_a),
              (:ordinary_membership_a, :support_a),
              (:member_membership_b, :support_b)
            """
        ),
        {**ids, "owner_role": owner_role, "admin_role": admin_role},
    )
    return owner_role, admin_role


async def _cleanup(session: AsyncSession, ids: dict[str, UUID]) -> None:
    await session.execute(
        text(
            """
            DELETE FROM membership_roles
            WHERE membership_id IN (
              :owner_membership_a, :owner2_membership_a, :admin_membership_a,
              :member_membership_a, :ordinary_membership_a, :member_membership_b
            )
            """
        ),
        ids,
    )
    await session.execute(
        text(
            """
            DELETE FROM memberships
            WHERE id IN (
              :owner_membership_a, :owner2_membership_a, :admin_membership_a,
              :member_membership_a, :ordinary_membership_a, :member_membership_b
            )
            """
        ),
        ids,
    )
    await session.execute(
        text(
            """
            DELETE FROM roles
            WHERE id IN (:support_a, :qa_a, :support_b, :platform_role)
            """
        ),
        ids,
    )
    for key in ("owner_a", "owner2_a", "admin_a", "member_a", "ordinary_a", "member_b"):
        await session.execute(text("DELETE FROM users WHERE id=:id"), {"id": ids[key]})
    await session.execute(
        text("DELETE FROM tenants WHERE id IN (:tenant_a, :tenant_b)"),
        ids,
    )


def test_member_management_tenant_scope_roles_and_last_owner() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        ids = _ids()
        transport = httpx.ASGITransport(app=app)
        try:
            async with session_factory() as session, session.begin():
                owner_role, admin_role = await _seed(session, ids)

            _install_overrides(session_factory, user_id=ids["owner_a"])
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                list_url = f"/api/v1/organizations/{ids['tenant_a']}/members"
                first_page = await client.get(list_url, params={"limit": 2, "offset": 0})
                assert first_page.status_code == 200
                first_items = first_page.json()["data"]
                assert len(first_items) == 2
                assert all(
                    "oidc_subject" not in item and "oidcSubject" not in item
                    for item in first_items
                )
                assert all(
                    "oidc_issuer" not in item and "oidcIssuer" not in item
                    for item in first_items
                )

                second_page = await client.get(list_url, params={"limit": 100, "offset": 2})
                assert second_page.status_code == 200
                all_a_ids = {
                    item["membershipId"]
                    for item in first_items + second_page.json()["data"]
                }
                assert str(ids["member_membership_b"]) not in all_a_ids
                assert {
                    str(ids["owner_membership_a"]),
                    str(ids["owner2_membership_a"]),
                    str(ids["admin_membership_a"]),
                    str(ids["member_membership_a"]),
                    str(ids["ordinary_membership_a"]),
                } == all_a_ids

                patch_url = (
                    f"/api/v1/organizations/{ids['tenant_a']}/members/"
                    f"{ids['member_membership_a']}"
                )
                valid_role = await client.patch(
                    patch_url,
                    json={"roleIds": [str(ids["qa_a"])]},
                )
                assert valid_role.status_code == 200
                assert [role["id"] for role in valid_role.json()["data"]["roles"]] == [
                    str(ids["qa_a"])
                ]

                duplicate = await client.patch(
                    patch_url,
                    json={"roleIds": [str(ids["qa_a"]), str(ids["qa_a"])]},
                )
                assert duplicate.status_code == 422

                foreign_role = await client.patch(
                    patch_url,
                    json={"roleIds": [str(ids["support_b"])]},
                )
                assert foreign_role.status_code == 422
                assert foreign_role.json()["error"]["code"] == "MEMBERSHIP_ROLE_INVALID"

                platform_role = await client.patch(
                    patch_url,
                    json={"roleIds": [str(ids["platform_role"])]},
                )
                assert platform_role.status_code == 422

                unknown_field = await client.patch(
                    patch_url,
                    json={"status": "active", "tenantId": str(ids["tenant_b"])},
                )
                assert unknown_field.status_code == 422

                suspended = await client.patch(patch_url, json={"status": "suspended"})
                assert suspended.status_code == 200
                assert suspended.json()["data"]["status"] == "suspended"

                foreign_member = await client.patch(
                    (
                        f"/api/v1/organizations/{ids['tenant_a']}/members/"
                        f"{ids['member_membership_b']}"
                    ),
                    json={"status": "suspended"},
                )
                assert foreign_member.status_code == 404

                foreign_list = await client.get(
                    f"/api/v1/organizations/{ids['tenant_b']}/members"
                )
                assert foreign_list.status_code == 404

                # Remove the owner role from one of two active owners. The requested
                # global admin role is assignable, leaving exactly one active owner.
                owner2_url = (
                    f"/api/v1/organizations/{ids['tenant_a']}/members/"
                    f"{ids['owner2_membership_a']}"
                )
                remove_one_owner = await client.patch(
                    owner2_url,
                    json={"roleIds": [str(admin_role)]},
                )
                assert remove_one_owner.status_code == 200

                last_owner_url = (
                    f"/api/v1/organizations/{ids['tenant_a']}/members/"
                    f"{ids['owner_membership_a']}"
                )
                suspend_last = await client.patch(last_owner_url, json={"status": "suspended"})
                assert suspend_last.status_code == 409
                assert suspend_last.json()["error"]["code"] == "LAST_ACTIVE_OWNER"

                remove_last_role = await client.patch(
                    last_owner_url,
                    json={"roleIds": [str(admin_role)]},
                )
                assert remove_last_role.status_code == 409

            # Admin has the same frozen management capability.
            _install_overrides(session_factory, user_id=ids["admin_a"])
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                admin_list = await client.get(
                    f"/api/v1/organizations/{ids['tenant_a']}/members"
                )
                assert admin_list.status_code == 200

            # An ordinary tenant role cannot manage members even though the user has
            # an active membership in the organization.
            _install_overrides(session_factory, user_id=ids["ordinary_a"])
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                denied_list = await client.get(
                    f"/api/v1/organizations/{ids['tenant_a']}/members"
                )
                assert denied_list.status_code == 403
                denied_patch = await client.patch(
                    (
                        f"/api/v1/organizations/{ids['tenant_a']}/members/"
                        f"{ids['member_membership_a']}"
                    ),
                    json={"status": "active"},
                )
                assert denied_patch.status_code == 403

            async with session_factory() as session:
                role_rows = (
                    await session.execute(
                        text(
                            """
                            SELECT mr.role_id
                            FROM membership_roles mr
                            WHERE mr.membership_id=:membership_id
                            """
                        ),
                        {"membership_id": ids["member_membership_a"]},
                    )
                ).scalars().all()
                assert role_rows == [ids["qa_a"]]
                last_owner_status = await session.scalar(
                    text("SELECT status FROM memberships WHERE id=:id"),
                    {"id": ids["owner_membership_a"]},
                )
                assert last_owner_status == "active"
                active_owner_count = await session.scalar(
                    text(
                        """
                        SELECT COUNT(DISTINCT m.id)
                        FROM memberships m
                        JOIN membership_roles mr ON mr.membership_id=m.id
                        JOIN roles r ON r.id=mr.role_id
                        WHERE m.tenant_id=:tenant_id AND m.status='active'
                          AND r.tenant_id IS NULL AND r.is_system=true AND r.key='owner'
                        """
                    ),
                    {"tenant_id": ids["tenant_a"]},
                )
                assert active_owner_count == 1
                assert owner_role != admin_role
        finally:
            _clear_overrides()
            async with session_factory() as session, session.begin():
                await _cleanup(session, ids)
            await engine.dispose()

    import asyncio

    asyncio.run(scenario())
