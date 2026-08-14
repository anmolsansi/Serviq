from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import load_settings
from app.core.database import create_database_engine

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)


async def _create_tenant(connection: AsyncConnection, slug: str) -> Any:
    result = await connection.execute(
        text(
            """
            INSERT INTO tenants (slug, display_name, status)
            VALUES (:slug, 'Invitation Test Tenant', 'active')
            RETURNING id
            """
        ),
        {"slug": slug},
    )
    return result.scalar_one()


async def _create_user(connection: AsyncConnection, subject: str) -> Any:
    result = await connection.execute(
        text(
            """
            INSERT INTO users (oidc_issuer, oidc_subject, email, display_name, status)
            VALUES ('https://issuer.example', :subject, :email, 'Invitation User', 'active')
            RETURNING id
            """
        ),
        {"subject": subject, "email": f"{subject}@example.com"},
    )
    return result.scalar_one()


async def _create_role(connection: AsyncConnection, tenant_id: Any, key: str) -> Any:
    result = await connection.execute(
        text(
            """
            INSERT INTO roles (tenant_id, key, display_name)
            VALUES (:tenant_id, :key, 'Invitation Role')
            RETURNING id
            """
        ),
        {"tenant_id": tenant_id, "key": key},
    )
    return result.scalar_one()


async def _create_invitation(
    connection: AsyncConnection,
    *,
    tenant_id: Any,
    invited_by_user_id: Any,
    email: str,
    token_hash: str,
    status: str = "pending",
) -> Any:
    result = await connection.execute(
        text(
            """
            INSERT INTO organization_invitations (
                tenant_id,
                email_normalized,
                token_hash,
                status,
                invited_by_user_id,
                expires_at
            )
            VALUES (
                :tenant_id,
                :email,
                :token_hash,
                :status,
                :invited_by_user_id,
                now() + interval '7 days'
            )
            RETURNING id
            """
        ),
        {
            "tenant_id": tenant_id,
            "email": email,
            "token_hash": token_hash,
            "status": status,
            "invited_by_user_id": invited_by_user_id,
        },
    )
    return result.scalar_one()


def _run_integrity_failure(
    scenario: Callable[[AsyncConnection], Awaitable[None]],
) -> None:
    async def run() -> None:
        engine = create_database_engine(load_settings())
        try:
            async with engine.begin() as connection:
                await scenario(connection)
        finally:
            await engine.dispose()

    with pytest.raises(IntegrityError):
        asyncio.run(run())


def _invitation_schema(connection: Connection) -> dict[str, Any]:
    inspector = inspect(connection)
    return {
        "columns": {column["name"] for column in inspector.get_columns("organization_invitations")},
        "indexes": {
            index["name"]: index for index in inspector.get_indexes("organization_invitations")
        },
        "foreign_keys": inspector.get_foreign_keys("organization_invitations"),
        "role_foreign_keys": inspector.get_foreign_keys("organization_invitation_roles"),
    }


def test_schema_has_hash_only_and_expected_fk_indexes() -> None:
    async def run() -> None:
        engine = create_database_engine(load_settings())
        try:
            async with engine.connect() as connection:
                snapshot = await connection.run_sync(_invitation_schema)
        finally:
            await engine.dispose()

        assert "token_hash" in snapshot["columns"]
        assert {"token", "raw_token", "invite_token", "invitation_token"}.isdisjoint(
            snapshot["columns"]
        )
        assert {
            "ix_organization_invitations_tenant_status_expires_at",
            "ix_organization_invitations_tenant_email_normalized",
            "ix_organization_invitations_invited_by_user_id",
            "ix_organization_invitations_accepted_by_user_id",
            "uq_organization_invitations_pending_tenant_email",
        } <= set(snapshot["indexes"])

        invitation_fk_columns = {
            tuple(fk["constrained_columns"]) for fk in snapshot["foreign_keys"]
        }
        assert ("tenant_id",) in invitation_fk_columns
        assert ("invited_by_user_id",) in invitation_fk_columns
        assert ("accepted_by_user_id",) in invitation_fk_columns

        role_fk_columns = {
            tuple(fk["constrained_columns"]) for fk in snapshot["role_foreign_keys"]
        }
        assert role_fk_columns == {("invitation_id",), ("role_id",)}

    asyncio.run(run())


def test_pending_unique_index_predicate_is_exactly_pending() -> None:
    async def run() -> None:
        engine = create_database_engine(load_settings())
        try:
            async with engine.connect() as connection:
                definition = (
                    await connection.execute(
                        text(
                            """
                            SELECT indexdef
                            FROM pg_indexes
                            WHERE schemaname = 'public'
                              AND indexname =
                                  'uq_organization_invitations_pending_tenant_email'
                            """
                        )
                    )
                ).scalar_one()
        finally:
            await engine.dispose()

        assert "UNIQUE INDEX" in definition
        assert "(tenant_id, email_normalized)" in definition
        assert "WHERE (status = 'pending'::text)" in definition

    asyncio.run(run())


def test_second_pending_invite_for_same_tenant_email_is_rejected() -> None:
    async def scenario(connection: AsyncConnection) -> None:
        tenant_id = await _create_tenant(connection, "pending-unique-tenant")
        user_id = await _create_user(connection, "pending-unique-user")
        await _create_invitation(
            connection,
            tenant_id=tenant_id,
            invited_by_user_id=user_id,
            email="invitee@example.com",
            token_hash="fake-hash-pending-1",
        )
        await _create_invitation(
            connection,
            tenant_id=tenant_id,
            invited_by_user_id=user_id,
            email="invitee@example.com",
            token_hash="fake-hash-pending-2",
        )

    _run_integrity_failure(scenario)


def test_historical_invite_does_not_block_new_pending_invite() -> None:
    async def run() -> None:
        engine = create_database_engine(load_settings())
        try:
            async with engine.begin() as connection:
                tenant_id = await _create_tenant(connection, "historical-invite-tenant")
                user_id = await _create_user(connection, "historical-invite-user")
                await _create_invitation(
                    connection,
                    tenant_id=tenant_id,
                    invited_by_user_id=user_id,
                    email="history@example.com",
                    token_hash="fake-hash-history-accepted",
                    status="accepted",
                )
                await _create_invitation(
                    connection,
                    tenant_id=tenant_id,
                    invited_by_user_id=user_id,
                    email="history@example.com",
                    token_hash="fake-hash-history-pending",
                )
                count = (
                    await connection.execute(
                        text(
                            """
                            SELECT count(*)
                            FROM organization_invitations
                            WHERE tenant_id = :tenant_id
                              AND email_normalized = 'history@example.com'
                            """
                        ),
                        {"tenant_id": tenant_id},
                    )
                ).scalar_one()
                assert count == 2
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_duplicate_token_hash_is_rejected_globally() -> None:
    async def scenario(connection: AsyncConnection) -> None:
        tenant_id = await _create_tenant(connection, "token-hash-tenant")
        user_id = await _create_user(connection, "token-hash-user")
        await _create_invitation(
            connection,
            tenant_id=tenant_id,
            invited_by_user_id=user_id,
            email="first@example.com",
            token_hash="fake-hash-global-duplicate",
        )
        await _create_invitation(
            connection,
            tenant_id=tenant_id,
            invited_by_user_id=user_id,
            email="second@example.com",
            token_hash="fake-hash-global-duplicate",
        )

    _run_integrity_failure(scenario)


def test_invalid_invitation_status_is_rejected() -> None:
    async def scenario(connection: AsyncConnection) -> None:
        tenant_id = await _create_tenant(connection, "invalid-status-tenant")
        user_id = await _create_user(connection, "invalid-status-user")
        await _create_invitation(
            connection,
            tenant_id=tenant_id,
            invited_by_user_id=user_id,
            email="status@example.com",
            token_hash="fake-hash-invalid-status",
            status="queued",
        )

    _run_integrity_failure(scenario)


def test_invalid_email_length_is_rejected() -> None:
    async def scenario(connection: AsyncConnection) -> None:
        tenant_id = await _create_tenant(connection, "invalid-email-tenant")
        user_id = await _create_user(connection, "invalid-email-user")
        await _create_invitation(
            connection,
            tenant_id=tenant_id,
            invited_by_user_id=user_id,
            email="x",
            token_hash="fake-hash-short-email",
        )

    _run_integrity_failure(scenario)


def test_duplicate_invitation_role_mapping_is_rejected() -> None:
    async def scenario(connection: AsyncConnection) -> None:
        tenant_id = await _create_tenant(connection, "duplicate-role-map-tenant")
        user_id = await _create_user(connection, "duplicate-role-map-user")
        role_id = await _create_role(connection, tenant_id, "duplicate-role-map")
        invitation_id = await _create_invitation(
            connection,
            tenant_id=tenant_id,
            invited_by_user_id=user_id,
            email="rolemap@example.com",
            token_hash="fake-hash-role-map",
        )
        statement = text(
            """
            INSERT INTO organization_invitation_roles (invitation_id, role_id)
            VALUES (:invitation_id, :role_id)
            """
        )
        values = {"invitation_id": invitation_id, "role_id": role_id}
        await connection.execute(statement, values)
        await connection.execute(statement, values)

    _run_integrity_failure(scenario)


def test_invitation_role_rejects_missing_role() -> None:
    async def scenario(connection: AsyncConnection) -> None:
        tenant_id = await _create_tenant(connection, "missing-role-tenant")
        user_id = await _create_user(connection, "missing-role-user")
        invitation_id = await _create_invitation(
            connection,
            tenant_id=tenant_id,
            invited_by_user_id=user_id,
            email="missingrole@example.com",
            token_hash="fake-hash-missing-role",
        )
        await connection.execute(
            text(
                """
                INSERT INTO organization_invitation_roles (invitation_id, role_id)
                VALUES (:invitation_id, '00000000-0000-0000-0000-000000000001')
                """
            ),
            {"invitation_id": invitation_id},
        )

    _run_integrity_failure(scenario)


def test_deleting_invitation_sets_membership_origin_to_null() -> None:
    async def run() -> None:
        engine = create_database_engine(load_settings())
        try:
            async with engine.begin() as connection:
                tenant_id = await _create_tenant(connection, "membership-origin-tenant")
                user_id = await _create_user(connection, "membership-origin-user")
                invitation_id = await _create_invitation(
                    connection,
                    tenant_id=tenant_id,
                    invited_by_user_id=user_id,
                    email="origin@example.com",
                    token_hash="fake-hash-membership-origin",
                )
                membership_id = (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO memberships (
                                tenant_id,
                                user_id,
                                status,
                                created_by_invitation_id
                            )
                            VALUES (:tenant_id, :user_id, 'active', :invitation_id)
                            RETURNING id
                            """
                        ),
                        {
                            "tenant_id": tenant_id,
                            "user_id": user_id,
                            "invitation_id": invitation_id,
                        },
                    )
                ).scalar_one()
                await connection.execute(
                    text("DELETE FROM organization_invitations WHERE id = :invitation_id"),
                    {"invitation_id": invitation_id},
                )
                origin = (
                    await connection.execute(
                        text(
                            """
                            SELECT created_by_invitation_id
                            FROM memberships
                            WHERE id = :membership_id
                            """
                        ),
                        {"membership_id": membership_id},
                    )
                ).scalar_one()
                assert origin is None
        finally:
            await engine.dispose()

    asyncio.run(run())
