from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import load_settings
from app.core.database import (
    create_database_engine,
    create_database_session_factory,
    get_database_session,
)
from app.core.principal import require_workforce_user_id
from app.main import app
from app.modules.organizations.models import Organization
from app.modules.organizations.schemas import OrganizationCreateRequest
from app.modules.organizations.service import create_organization
from app.modules.tenancy.models import Membership, MembershipRole, Role

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)


def _user_row(user_id: UUID) -> dict[str, object]:
    return {
        "id": user_id,
        "subject": f"subject-{user_id.hex}",
        "email": f"ope283-{user_id.hex}@example.com",
    }


async def _insert_users(session: AsyncSession, user_ids: tuple[UUID, ...]) -> None:
    for user_id in user_ids:
        await session.execute(
            text(
                """
                INSERT INTO users (id, oidc_issuer, oidc_subject, email, display_name, status)
                VALUES (:id, 'https://ope283.test', :subject, :email, 'OPE 283 User', 'active')
                """
            ),
            _user_row(user_id),
        )


async def _cleanup(session: AsyncSession, user_ids: tuple[UUID, ...], prefix: str) -> None:
    for user_id in user_ids:
        await session.execute(
            text(
                """
                DELETE FROM membership_roles
                WHERE membership_id IN (
                    SELECT id FROM memberships WHERE user_id = :user_id
                )
                """
            ),
            {"user_id": user_id},
        )
        await session.execute(
            text("DELETE FROM memberships WHERE user_id = :user_id"),
            {"user_id": user_id},
        )
        await session.execute(
            text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": user_id},
        )
    await session.execute(
        text("DELETE FROM tenants WHERE slug LIKE :prefix"),
        {"prefix": f"{prefix}%"},
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


def test_organization_list_create_and_cross_user_isolation() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        user_a = uuid4()
        user_b = uuid4()
        users = (user_a, user_b)
        prefix = f"ope283-{uuid4().hex[:10]}-"
        try:
            async with session_factory() as session, session.begin():
                await _insert_users(session, users)

            _install_overrides(session_factory, user_a)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                empty = await client.get("/api/v1/organizations")
                assert empty.status_code == 200
                assert empty.json() == {"data": []}

                first = await client.post(
                    "/api/v1/organizations",
                    json={"slug": f"{prefix}one", "displayName": " First Organization "},
                )
                second = await client.post(
                    "/api/v1/organizations",
                    json={"slug": f"{prefix}two", "displayName": "Second Organization"},
                )
                assert first.status_code == 201
                assert first.json()["data"]["displayName"] == "First Organization"
                assert second.status_code == 201

                listed = await client.get("/api/v1/organizations")
                assert listed.status_code == 200
                assert {item["slug"] for item in listed.json()["data"]} == {
                    f"{prefix}one",
                    f"{prefix}two",
                }

                duplicate = await client.post(
                    "/api/v1/organizations",
                    json={"slug": f"{prefix}one", "displayName": "Duplicate"},
                )
                assert duplicate.status_code == 409
                assert duplicate.json()["error"]["code"] == "ORGANIZATION_SLUG_CONFLICT"

            _install_overrides(session_factory, user_b)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                other = await client.get("/api/v1/organizations")
                assert other.status_code == 200
                assert other.json() == {"data": []}

            async with session_factory() as session:
                owner_role_id = await session.scalar(
                    select(Role.id).where(
                        Role.tenant_id.is_(None),
                        Role.is_system.is_(True),
                        Role.key == "owner",
                    )
                )
                assert owner_role_id is not None
                memberships = await session.scalars(
                    select(Membership).where(Membership.user_id == user_a)
                )
                membership_rows = tuple(memberships.all())
                assert len(membership_rows) == 2
                assert all(item.status == "active" for item in membership_rows)
                mapping_count = await session.scalar(
                    select(func.count(MembershipRole.id)).where(
                        MembershipRole.membership_id.in_([row.id for row in membership_rows]),
                        MembershipRole.role_id == owner_role_id,
                    )
                )
                assert mapping_count == 2
        finally:
            _clear_overrides()
            async with session_factory() as session, session.begin():
                await _cleanup(session, users, prefix)
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "body",
    [
        {"slug": "Uppercase", "displayName": "Name"},
        {"slug": "-leading", "displayName": "Name"},
        {"slug": "trailing-", "displayName": "Name"},
        {"slug": "ab", "displayName": "Name"},
        {"slug": "valid-slug", "displayName": "   "},
        {"slug": "valid-slug", "displayName": "x" * 121},
        {"slug": "valid-slug", "displayName": "Name", "userId": str(uuid4())},
    ],
)
def test_organization_create_validation_uses_frozen_error_envelope(body: dict[str, object]) -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        user_id = uuid4()
        try:
            async with session_factory() as session, session.begin():
                await _insert_users(session, (user_id,))
            _install_overrides(session_factory, user_id)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/api/v1/organizations", json=body)
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        finally:
            _clear_overrides()
            async with session_factory() as session, session.begin():
                await _cleanup(session, (user_id,), "ope283-validation-")
            await engine.dispose()

    asyncio.run(scenario())


def test_organization_routes_reject_missing_server_owned_principal() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        try:
            _install_overrides(session_factory, None)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/v1/organizations")
            assert response.status_code == 401
            assert response.json() == {
                "error": {"code": "UNAUTHENTICATED", "message": "Authentication required."}
            }
        finally:
            _clear_overrides()
            await engine.dispose()

    asyncio.run(scenario())


def test_owner_mapping_failure_rolls_back_organization_and_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        from app.modules.organizations import service as organization_service

        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        user_id = uuid4()
        prefix = f"ope283-rollback-{uuid4().hex[:8]}"

        def fail_mapping(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("simulated mapping failure")

        try:
            async with session_factory() as session, session.begin():
                await _insert_users(session, (user_id,))
            monkeypatch.setattr(organization_service, "add_membership_role", fail_mapping)

            async with session_factory() as session:
                with pytest.raises(RuntimeError, match="simulated mapping failure"):
                    await create_organization(
                        session,
                        user_id=user_id,
                        request=OrganizationCreateRequest(
                            slug=prefix,
                            displayName="Rollback Organization",
                        ),
                    )

            async with session_factory() as session:
                tenant_count = await session.scalar(
                    select(func.count(Organization.id)).where(Organization.slug == prefix)
                )
                membership_count = await session.scalar(
                    select(func.count(Membership.id)).where(Membership.user_id == user_id)
                )
                assert tenant_count == 0
                assert membership_count == 0
        finally:
            async with session_factory() as session, session.begin():
                await _cleanup(session, (user_id,), prefix)
            await engine.dispose()

    asyncio.run(scenario())
