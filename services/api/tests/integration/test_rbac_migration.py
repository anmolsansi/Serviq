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


async def _create_tenant(connection: AsyncConnection, slug: str = "acme") -> Any:
    result = await connection.execute(
        text(
            """
            INSERT INTO tenants (slug, display_name, status)
            VALUES (:slug, 'Acme', 'active')
            RETURNING id
            """
        ),
        {"slug": slug},
    )
    return result.scalar_one()


async def _create_user(connection: AsyncConnection, subject: str = "user-1") -> Any:
    result = await connection.execute(
        text(
            """
            INSERT INTO users (oidc_issuer, oidc_subject, email, display_name, status)
            VALUES ('https://issuer.example', :subject, :email, 'User', 'active')
            RETURNING id
            """
        ),
        {"subject": subject, "email": f"{subject}@example.com"},
    )
    return result.scalar_one()


def _run_failure_scenario(scenario: Callable[[AsyncConnection], Awaitable[None]]) -> None:
    async def run() -> None:
        engine = create_database_engine(load_settings())
        try:
            async with engine.begin() as connection:
                await scenario(connection)
        finally:
            await engine.dispose()

    with pytest.raises(IntegrityError):
        asyncio.run(run())


def _schema_snapshot(connection: Connection) -> dict[str, Any]:
    inspector = inspect(connection)
    return {
        "tables": set(inspector.get_table_names(schema="public")),
        "membership_columns": {
            column["name"]: column for column in inspector.get_columns("memberships")
        },
        "membership_fks": inspector.get_foreign_keys("memberships"),
        "membership_indexes": {
            index["name"] for index in inspector.get_indexes("memberships")
        },
    }


def test_schema_contains_exact_six_product_tables_and_deferred_invitation_fk() -> None:
    async def run() -> None:
        engine = create_database_engine(load_settings())
        try:
            async with engine.connect() as connection:
                snapshot = await connection.run_sync(_schema_snapshot)
        finally:
            await engine.dispose()

        assert snapshot["tables"] == {
            "alembic_version",
            "tenants",
            "users",
            "memberships",
            "roles",
            "role_permissions",
            "membership_roles",
        }
        invitation_column = snapshot["membership_columns"]["created_by_invitation_id"]
        assert invitation_column["nullable"] is True
        assert "ix_memberships_created_by_invitation_id" in snapshot["membership_indexes"]
        assert all(
            fk["constrained_columns"] != ["created_by_invitation_id"]
            for fk in snapshot["membership_fks"]
        )

    asyncio.run(run())


def test_duplicate_tenant_slug_is_rejected() -> None:
    async def scenario(connection: AsyncConnection) -> None:
        await _create_tenant(connection, "duplicate-tenant")
        await _create_tenant(connection, "duplicate-tenant")

    _run_failure_scenario(scenario)


def test_duplicate_oidc_identity_is_rejected() -> None:
    async def scenario(connection: AsyncConnection) -> None:
        await _create_user(connection, "same-subject")
        await connection.execute(
            text(
                """
                INSERT INTO users
                    (oidc_issuer, oidc_subject, email, display_name, status)
                VALUES
                    ('https://issuer.example', 'same-subject', 'other@example.com', 'Other', 'active')
                """
            )
        )

    _run_failure_scenario(scenario)


def test_duplicate_membership_is_rejected() -> None:
    async def scenario(connection: AsyncConnection) -> None:
        tenant_id = await _create_tenant(connection, "membership-tenant")
        user_id = await _create_user(connection, "membership-user")
        statement = text(
            """
            INSERT INTO memberships (tenant_id, user_id, status)
            VALUES (:tenant_id, :user_id, 'active')
            """
        )
        values = {"tenant_id": tenant_id, "user_id": user_id}
        await connection.execute(statement, values)
        await connection.execute(statement, values)

    _run_failure_scenario(scenario)


def test_invalid_tenant_status_is_rejected() -> None:
    async def scenario(connection: AsyncConnection) -> None:
        await connection.execute(
            text(
                """
                INSERT INTO tenants (slug, display_name, status)
                VALUES ('bad-status-tenant', 'Bad', 'pending')
                """
            )
        )

    _run_failure_scenario(scenario)


def test_invalid_user_status_is_rejected() -> None:
    async def scenario(connection: AsyncConnection) -> None:
        await connection.execute(
            text(
                """
                INSERT INTO users (oidc_issuer, oidc_subject, email, display_name, status)
                VALUES ('https://issuer.example', 'bad-user', 'bad@example.com', 'Bad', 'pending')
                """
            )
        )

    _run_failure_scenario(scenario)


def test_invalid_membership_status_is_rejected() -> None:
    async def scenario(connection: AsyncConnection) -> None:
        tenant_id = await _create_tenant(connection, "bad-membership-tenant")
        user_id = await _create_user(connection, "bad-membership-user")
        await connection.execute(
            text(
                """
                INSERT INTO memberships (tenant_id, user_id, status)
                VALUES (:tenant_id, :user_id, 'pending')
                """
            ),
            {"tenant_id": tenant_id, "user_id": user_id},
        )

    _run_failure_scenario(scenario)


def test_duplicate_membership_role_mapping_is_rejected() -> None:
    async def scenario(connection: AsyncConnection) -> None:
        tenant_id = await _create_tenant(connection, "mapping-tenant")
        user_id = await _create_user(connection, "mapping-user")
        membership_id = (
            await connection.execute(
                text(
                    """
                    INSERT INTO memberships (tenant_id, user_id, status)
                    VALUES (:tenant_id, :user_id, 'active')
                    RETURNING id
                    """
                ),
                {"tenant_id": tenant_id, "user_id": user_id},
            )
        ).scalar_one()
        role_id = (
            await connection.execute(
                text(
                    """
                    INSERT INTO roles (tenant_id, key, display_name)
                    VALUES (:tenant_id, 'support-agent', 'Support Agent')
                    RETURNING id
                    """
                ),
                {"tenant_id": tenant_id},
            )
        ).scalar_one()
        statement = text(
            """
            INSERT INTO membership_roles (membership_id, role_id)
            VALUES (:membership_id, :role_id)
            """
        )
        values = {"membership_id": membership_id, "role_id": role_id}
        await connection.execute(statement, values)
        await connection.execute(statement, values)

    _run_failure_scenario(scenario)


def test_duplicate_role_permission_is_rejected() -> None:
    async def scenario(connection: AsyncConnection) -> None:
        tenant_id = await _create_tenant(connection, "permission-tenant")
        role_id = (
            await connection.execute(
                text(
                    """
                    INSERT INTO roles (tenant_id, key, display_name)
                    VALUES (:tenant_id, 'admin', 'Admin')
                    RETURNING id
                    """
                ),
                {"tenant_id": tenant_id},
            )
        ).scalar_one()
        statement = text(
            """
            INSERT INTO role_permissions (role_id, permission_key)
            VALUES (:role_id, 'conversations.read')
            """
        )
        await connection.execute(statement, {"role_id": role_id})
        await connection.execute(statement, {"role_id": role_id})

    _run_failure_scenario(scenario)


def test_global_role_keys_use_nulls_not_distinct_uniqueness() -> None:
    async def scenario(connection: AsyncConnection) -> None:
        statement = text(
            """
            INSERT INTO roles (tenant_id, key, display_name, is_system)
            VALUES (NULL, 'platform-operator', 'Platform Operator', true)
            """
        )
        await connection.execute(statement)
        await connection.execute(statement)

    _run_failure_scenario(scenario)


def test_role_unique_constraint_is_nulls_not_distinct() -> None:
    async def run() -> None:
        engine = create_database_engine(load_settings())
        try:
            async with engine.connect() as connection:
                definition = (
                    await connection.execute(
                        text(
                            """
                            SELECT pg_get_constraintdef(oid)
                            FROM pg_constraint
                            WHERE conname = 'uq_roles_tenant_key'
                            """
                        )
                    )
                ).scalar_one()
        finally:
            await engine.dispose()

        assert "UNIQUE NULLS NOT DISTINCT (tenant_id, key)" in definition

    asyncio.run(run())
