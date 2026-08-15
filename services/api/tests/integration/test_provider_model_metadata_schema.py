from __future__ import annotations

import asyncio
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.core.config import load_settings
from app.core.database import create_database_engine, create_database_session_factory

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)


async def _expect_integrity_error(session_factory: object, statement: str, params: dict[str, object]) -> None:
    # Kept local to this schema test so every invalid row executes in its own
    # transaction and cannot poison the following PostgreSQL assertion.
    async with session_factory() as session:  # type: ignore[operator]
        with pytest.raises(IntegrityError):
            async with session.begin():
                await session.execute(text(statement), params)


def test_provider_and_model_metadata_schema_constraints() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        tenant_a = uuid4()
        tenant_b = uuid4()
        user_id = uuid4()
        provider_a = uuid4()
        provider_b = uuid4()
        try:
            async with session_factory() as session, session.begin():
                await session.execute(
                    text(
                        """
                        INSERT INTO tenants (id, slug, display_name, status, default_locale)
                        VALUES (:a, :slug_a, 'Provider Tenant', 'active', 'en'),
                               (:b, :slug_b, 'Provider Tenant', 'active', 'en')
                        """
                    ),
                    {
                        "a": tenant_a,
                        "b": tenant_b,
                        "slug_a": f"provider-a-{tenant_a.hex[:12]}",
                        "slug_b": f"provider-b-{tenant_b.hex[:12]}",
                    },
                )
                await session.execute(
                    text(
                        """
                        INSERT INTO users (
                          id, oidc_issuer, oidc_subject, email, display_name, status
                        ) VALUES (
                          :id, 'https://ope289.test', :subject,
                          'provider-owner@example.com', 'Provider Owner', 'active'
                        )
                        """
                    ),
                    {"id": user_id, "subject": f"owner-{user_id.hex}"},
                )
                await session.execute(
                    text(
                        """
                        INSERT INTO provider_connections (
                          id, tenant_id, provider, display_name, secret_ref,
                          status, created_by
                        ) VALUES (
                          :id, :tenant, 'openai', 'Primary AI',
                          'secretref_fake_001', 'untested', :created_by
                        )
                        """
                    ),
                    {"id": provider_a, "tenant": tenant_a, "created_by": user_id},
                )
                await session.execute(
                    text(
                        """
                        INSERT INTO provider_connections (
                          id, tenant_id, provider, display_name, secret_ref,
                          status, created_by
                        ) VALUES (
                          :id, :tenant, 'anthropic', 'Primary AI',
                          'secretref_fake_002', 'active', :created_by
                        )
                        """
                    ),
                    {"id": provider_b, "tenant": tenant_b, "created_by": user_id},
                )
                await session.execute(
                    text(
                        """
                        INSERT INTO model_configurations (
                          tenant_id, provider_connection_id, alias,
                          upstream_model, purpose
                        ) VALUES (
                          :tenant, :provider, 'support-default',
                          'fake-upstream-generation-model', 'generation'
                        )
                        """
                    ),
                    {"tenant": tenant_a, "provider": provider_a},
                )

            provider_insert = """
                INSERT INTO provider_connections (
                  tenant_id, provider, display_name, secret_ref, status, created_by
                ) VALUES (
                  :tenant, :provider, :display_name, 'secretref_fake_invalid',
                  :status, :created_by
                )
            """
            await _expect_integrity_error(
                session_factory,
                provider_insert,
                {
                    "tenant": tenant_a,
                    "provider": "unsupported",
                    "display_name": "Bad Provider",
                    "status": "untested",
                    "created_by": user_id,
                },
            )
            await _expect_integrity_error(
                session_factory,
                provider_insert,
                {
                    "tenant": tenant_a,
                    "provider": "openai",
                    "display_name": "Bad Status",
                    "status": "connected",
                    "created_by": user_id,
                },
            )
            await _expect_integrity_error(
                session_factory,
                provider_insert,
                {
                    "tenant": tenant_a,
                    "provider": "openai",
                    "display_name": "Primary AI",
                    "status": "untested",
                    "created_by": user_id,
                },
            )

            model_insert = """
                INSERT INTO model_configurations (
                  tenant_id, provider_connection_id, alias, upstream_model, purpose
                ) VALUES (:tenant, :provider, :alias, :upstream, :purpose)
            """
            await _expect_integrity_error(
                session_factory,
                model_insert,
                {
                    "tenant": tenant_a,
                    "provider": provider_a,
                    "alias": "bad-purpose",
                    "upstream": "fake-model",
                    "purpose": "chat",
                },
            )
            await _expect_integrity_error(
                session_factory,
                model_insert,
                {
                    "tenant": tenant_a,
                    "provider": provider_a,
                    "alias": "support-default",
                    "upstream": "fake-model",
                    "purpose": "generation",
                },
            )
            await _expect_integrity_error(
                session_factory,
                model_insert,
                {
                    "tenant": tenant_a,
                    "provider": uuid4(),
                    "alias": "missing-provider",
                    "upstream": "fake-model",
                    "purpose": "generation",
                },
            )

            async with engine.connect() as connection:
                def inspect_columns(sync_connection: object) -> set[str]:
                    return {
                        column["name"]
                        for column in inspect(sync_connection).get_columns(
                            "provider_connections"
                        )
                    }

                columns = await connection.run_sync(inspect_columns)
            forbidden = {"api_key", "secret", "token", "credential", "credentials"}
            assert columns.isdisjoint(forbidden)
            assert "secret_ref" in columns
        finally:
            async with session_factory() as session, session.begin():
                await session.execute(
                    text("DELETE FROM model_configurations WHERE tenant_id IN (:a, :b)"),
                    {"a": tenant_a, "b": tenant_b},
                )
                await session.execute(
                    text("DELETE FROM provider_connections WHERE tenant_id IN (:a, :b)"),
                    {"a": tenant_a, "b": tenant_b},
                )
                await session.execute(text("DELETE FROM users WHERE id=:id"), {"id": user_id})
                await session.execute(
                    text("DELETE FROM tenants WHERE id IN (:a, :b)"),
                    {"a": tenant_a, "b": tenant_b},
                )
            await engine.dispose()

    asyncio.run(scenario())
