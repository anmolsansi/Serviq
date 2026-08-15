from __future__ import annotations

import asyncio
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.core.config import load_settings
from app.core.database import create_database_engine, create_database_session_factory
from app.modules.tenancy.errors import TenantMembershipAccessError
from app.modules.tenancy.service import resolve_tenant_membership

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)


async def _insert_fixture(session: object, ids: dict[str, UUID]) -> None:
    # The integration fixture intentionally includes a cross-tenant role mapping that
    # the database FKs permit structurally. The resolver must still filter it out.
    await session.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, status)
            VALUES (:tenant_a, :slug_a, 'Tenant A', 'active'),
                   (:tenant_b, :slug_b, 'Tenant B', 'active'),
                   (:tenant_c, :slug_c, 'Tenant C', 'active')
            """
        ),
        {
            "tenant_a": ids["tenant_a"],
            "tenant_b": ids["tenant_b"],
            "tenant_c": ids["tenant_c"],
            "slug_a": f"ope282-a-{ids['tenant_a'].hex[:12]}",
            "slug_b": f"ope282-b-{ids['tenant_b'].hex[:12]}",
            "slug_c": f"ope282-c-{ids['tenant_c'].hex[:12]}",
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO users (id, oidc_issuer, oidc_subject, email, display_name, status)
            VALUES (:user_id, 'https://ope282.test', :subject, :email, 'OPE 282 User', 'active')
            """
        ),
        {
            "user_id": ids["user"],
            "subject": f"subject-{ids['user'].hex}",
            "email": f"ope282-{ids['user'].hex}@example.com",
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO memberships (id, tenant_id, user_id, status)
            VALUES (:membership_a, :tenant_a, :user_id, 'active'),
                   (:membership_b, :tenant_b, :user_id, 'suspended')
            """
        ),
        ids,
    )
    await session.execute(
        text(
            """
            INSERT INTO roles (id, tenant_id, key, display_name, is_system)
            VALUES (:role_a1, :tenant_a, 'reader', 'Reader A', false),
                   (:role_a2, :tenant_a, 'editor', 'Editor A', false),
                   (:role_b, :tenant_b, 'reader', 'Reader B', false),
                   (:system_role, NULL, 'system_support', 'System Support', true),
                   (:invalid_global_role, NULL, 'global_custom', 'Global Custom', false)
            """
        ),
        ids,
    )
    await session.execute(
        text(
            """
            INSERT INTO role_permissions (role_id, permission_key)
            VALUES (:role_a1, 'organization.read'),
                   (:role_a1, 'shared.permission'),
                   (:role_a2, 'organization.write'),
                   (:role_a2, 'shared.permission'),
                   (:role_b, 'tenant-b.secret'),
                   (:system_role, 'system.support'),
                   (:invalid_global_role, 'invalid.global')
            """
        ),
        ids,
    )
    await session.execute(
        text(
            """
            INSERT INTO membership_roles (membership_id, role_id)
            VALUES (:membership_a, :role_a1),
                   (:membership_a, :role_a2),
                   (:membership_a, :role_b),
                   (:membership_a, :system_role),
                   (:membership_a, :invalid_global_role)
            """
        ),
        ids,
    )


def _ids() -> dict[str, UUID]:
    return {
        key: uuid4()
        for key in (
            "tenant_a",
            "tenant_b",
            "tenant_c",
            "user",
            "membership_a",
            "membership_b",
            "role_a1",
            "role_a2",
            "role_b",
            "system_role",
            "invalid_global_role",
        )
    }


def test_tenant_capabilities_are_deduplicated_and_tenant_safe() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        ids = _ids()
        try:
            async with session_factory() as session, session.begin():
                await _insert_fixture(session, ids)

            async with session_factory() as session:
                resolved = await resolve_tenant_membership(
                    session,
                    user_id=ids["user"],
                    tenant_id=ids["tenant_a"],
                )

            assert resolved.membership_id == ids["membership_a"]
            assert resolved.status == "active"
            assert resolved.permissions == (
                "organization.read",
                "organization.write",
                "shared.permission",
                "system.support",
            )
            assert "tenant-b.secret" not in resolved.permissions
            assert "invalid.global" not in resolved.permissions
        finally:
            async with session_factory() as session, session.begin():
                await session.execute(
                    text("DELETE FROM tenants WHERE id IN (:a, :b, :c)"),
                    {"a": ids["tenant_a"], "b": ids["tenant_b"], "c": ids["tenant_c"]},
                )
            await engine.dispose()

    asyncio.run(scenario())


def test_suspended_and_missing_memberships_fail_closed() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        ids = _ids()
        try:
            async with session_factory() as session, session.begin():
                await _insert_fixture(session, ids)

            async with session_factory() as session:
                with pytest.raises(TenantMembershipAccessError):
                    await resolve_tenant_membership(
                        session,
                        user_id=ids["user"],
                        tenant_id=ids["tenant_b"],
                    )

            async with session_factory() as session:
                with pytest.raises(TenantMembershipAccessError):
                    await resolve_tenant_membership(
                        session,
                        user_id=ids["user"],
                        tenant_id=ids["tenant_c"],
                    )
        finally:
            async with session_factory() as session, session.begin():
                await session.execute(
                    text("DELETE FROM tenants WHERE id IN (:a, :b, :c)"),
                    {"a": ids["tenant_a"], "b": ids["tenant_b"], "c": ids["tenant_c"]},
                )
            await engine.dispose()

    asyncio.run(scenario())
