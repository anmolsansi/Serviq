from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
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
from app.core.principal import require_workforce_user_id
from app.main import app
from tests.support.tenant_isolation import (
    TenantIsolationFixture,
    assert_foreign_resource_hidden,
    assert_list_excludes_foreign,
    assert_value_unchanged,
    cleanup_tenant_isolation_fixture,
    seed_tenant_isolation_fixture,
)

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)


def _install_overrides(
    session_factory: async_sessionmaker[AsyncSession],
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


def test_tenant_isolation_harness_covers_organization_and_membership_attacks() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        fixture = TenantIsolationFixture.new()
        transport = httpx.ASGITransport(app=app)
        try:
            async with session_factory() as session, session.begin():
                await seed_tenant_isolation_fixture(session, fixture)

            _install_overrides(session_factory, fixture.owner_a)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                member_list = await client.get(
                    f"/api/v1/organizations/{fixture.tenant_a}/members"
                )
                assert member_list.status_code == 200
                assert_list_excludes_foreign(
                    member_list.json()["data"],
                    foreign_id=fixture.member_membership_b,
                    id_of=lambda item: UUID(item["membershipId"]),
                )

                foreign_org_get = await client.get(
                    f"/api/v1/organizations/{fixture.tenant_b}"
                )
                assert_foreign_resource_hidden(foreign_org_get.status_code)

                async with session_factory() as session:
                    before_org_name = await session.scalar(
                        text("SELECT display_name FROM tenants WHERE id=:id"),
                        {"id": fixture.tenant_b},
                    )
                    before_member_status = await session.scalar(
                        text("SELECT status FROM memberships WHERE id=:id"),
                        {"id": fixture.member_membership_b},
                    )

                foreign_org_patch = await client.patch(
                    f"/api/v1/organizations/{fixture.tenant_b}",
                    json={"displayName": "Cross Tenant Mutation"},
                )
                assert_foreign_resource_hidden(foreign_org_patch.status_code)

                foreign_member_patch = await client.patch(
                    (
                        f"/api/v1/organizations/{fixture.tenant_a}/members/"
                        f"{fixture.member_membership_b}"
                    ),
                    json={"status": "suspended"},
                )
                assert_foreign_resource_hidden(foreign_member_patch.status_code)

                async with session_factory() as session:
                    after_org_name = await session.scalar(
                        text("SELECT display_name FROM tenants WHERE id=:id"),
                        {"id": fixture.tenant_b},
                    )
                    after_member_status = await session.scalar(
                        text("SELECT status FROM memberships WHERE id=:id"),
                        {"id": fixture.member_membership_b},
                    )
                assert_value_unchanged(before=before_org_name, after=after_org_name)
                assert_value_unchanged(
                    before=before_member_status,
                    after=after_member_status,
                )

            # Reverse tenant direction to prove fixture/test order does not encode A as
            # globally privileged. Tenant B's owner must be equally unable to see A.
            _install_overrides(session_factory, fixture.owner_b)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                reverse_get = await client.get(
                    f"/api/v1/organizations/{fixture.tenant_a}"
                )
                assert_foreign_resource_hidden(reverse_get.status_code)
                reverse_list = await client.get(
                    f"/api/v1/organizations/{fixture.tenant_b}/members"
                )
                assert reverse_list.status_code == 200
                assert_list_excludes_foreign(
                    reverse_list.json()["data"],
                    foreign_id=fixture.member_membership_a,
                    id_of=lambda item: UUID(item["membershipId"]),
                )
        finally:
            _clear_overrides()
            async with session_factory() as session, session.begin():
                await cleanup_tenant_isolation_fixture(session, fixture)
            await engine.dispose()

    asyncio.run(scenario())
