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
    names = (
        "tenant_a",
        "tenant_b",
        "owner",
        "ordinary",
        "foreign",
        "provider_active",
        "provider_alt",
        "provider_disabled",
        "provider_untested",
        "provider_foreign",
    )
    ids = {name: uuid4() for name in names}
    owner_role = await _global_role_id(session, "owner")
    ordinary_role = uuid4()
    ids["ordinary_role"] = ordinary_role

    await session.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, status, default_locale)
            VALUES (:tenant_a, :slug_a, 'Model Team A', 'active', 'en'),
                   (:tenant_b, :slug_b, 'Model Team B', 'active', 'en')
            """
        ),
        {
            **ids,
            "slug_a": f"model-crud-a-{ids['tenant_a'].hex[:10]}",
            "slug_b": f"model-crud-b-{ids['tenant_b'].hex[:10]}",
        },
    )
    for key in ("owner", "ordinary", "foreign"):
        await session.execute(
            text(
                """
                INSERT INTO users (
                  id, oidc_issuer, oidc_subject, email, display_name, status
                ) VALUES (
                  :id, 'https://ope299.test', :subject, :email, :name, 'active'
                )
                """
            ),
            {
                "id": ids[key],
                "subject": f"{key}-{ids[key].hex}",
                "email": f"{key}-{ids[key].hex[:8]}@example.com",
                "name": key.title(),
            },
        )

    await session.execute(
        text(
            """
            INSERT INTO roles (id, tenant_id, key, display_name, is_system)
            VALUES (:id, :tenant, :key, 'No AI Provider Permission', false)
            """
        ),
        {
            "id": ordinary_role,
            "tenant": ids["tenant_a"],
            "key": f"ordinary-model-{ordinary_role.hex}",
        },
    )

    memberships = {
        "owner_membership": uuid4(),
        "ordinary_membership": uuid4(),
        "foreign_membership": uuid4(),
    }
    ids.update(memberships)
    await session.execute(
        text(
            """
            INSERT INTO memberships (id, tenant_id, user_id, status)
            VALUES (:owner_membership, :tenant_a, :owner, 'active'),
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
            VALUES (:owner_membership, :owner_role),
                   (:ordinary_membership, :ordinary_role),
                   (:foreign_membership, :owner_role)
            """
        ),
        {**ids, "owner_role": owner_role},
    )

    provider_rows = (
        (
            ids["provider_active"],
            ids["tenant_a"],
            "openai",
            "Active Primary",
            "active",
            ids["owner"],
        ),
        (
            ids["provider_alt"],
            ids["tenant_a"],
            "anthropic",
            "Active Alternate",
            "active",
            ids["owner"],
        ),
        (
            ids["provider_disabled"],
            ids["tenant_a"],
            "gemini",
            "Disabled Provider",
            "disabled",
            ids["owner"],
        ),
        (
            ids["provider_untested"],
            ids["tenant_a"],
            "openrouter",
            "Untested Provider",
            "untested",
            ids["owner"],
        ),
        (
            ids["provider_foreign"],
            ids["tenant_b"],
            "openai",
            "Foreign Active",
            "active",
            ids["foreign"],
        ),
    )
    for provider_id, tenant_id, provider, display_name, status, created_by in provider_rows:
        await session.execute(
            text(
                """
                INSERT INTO provider_connections (
                  id, tenant_id, provider, display_name, secret_ref,
                  status, created_by
                ) VALUES (
                  :id, :tenant, :provider, :display_name, :secret_ref,
                  :status, :created_by
                )
                """
            ),
            {
                "id": provider_id,
                "tenant": tenant_id,
                "provider": provider,
                "display_name": display_name,
                "secret_ref": f"secretref_ope299_{provider_id.hex}",
                "status": status,
                "created_by": created_by,
            },
        )
    return ids


async def _cleanup(session: AsyncSession, ids: dict[str, UUID]) -> None:
    await session.execute(
        text(
            """
            DELETE FROM model_configuration_references
            WHERE tenant_id IN (:a, :b)
            """
        ),
        {"a": ids["tenant_a"], "b": ids["tenant_b"]},
    )
    await session.execute(
        text("DELETE FROM model_configurations WHERE tenant_id IN (:a, :b)"),
        {"a": ids["tenant_a"], "b": ids["tenant_b"]},
    )
    await session.execute(
        text("DELETE FROM provider_connections WHERE tenant_id IN (:a, :b)"),
        {"a": ids["tenant_a"], "b": ids["tenant_b"]},
    )
    await session.execute(
        text(
            """
            DELETE FROM membership_roles WHERE membership_id IN (
              :owner_membership, :ordinary_membership, :foreign_membership
            )
            """
        ),
        ids,
    )
    await session.execute(
        text(
            """
            DELETE FROM memberships WHERE id IN (
              :owner_membership, :ordinary_membership, :foreign_membership
            )
            """
        ),
        ids,
    )
    await session.execute(text("DELETE FROM roles WHERE id=:id"), {"id": ids["ordinary_role"]})
    await session.execute(
        text("DELETE FROM users WHERE id IN (:owner, :ordinary, :foreign)"),
        ids,
    )
    await session.execute(
        text("DELETE FROM tenants WHERE id IN (:a, :b)"),
        {"a": ids["tenant_a"], "b": ids["tenant_b"]},
    )


def _create_payload(
    provider_connection_id: UUID,
    *,
    alias: str,
    upstream_model: str,
    purpose: str = "generation",
    enabled: bool = True,
) -> dict[str, object]:
    return {
        "providerConnectionId": str(provider_connection_id),
        "alias": alias,
        "upstreamModel": upstream_model,
        "purpose": purpose,
        "enabled": enabled,
    }


def test_model_configuration_crud_validation_authorization_and_reference_protection() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        transport = httpx.ASGITransport(app=app)
        ids: dict[str, UUID] = {}
        try:
            async with session_factory() as session, session.begin():
                ids = await _seed(session)

            _install_overrides(
                session_factory,
                user_id=ids["owner"],
                tenant_id=ids["tenant_a"],
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                generation = await client.post(
                    "/api/v1/models",
                    json=_create_payload(
                        ids["provider_active"],
                        alias="  support-primary  ",
                        upstream_model="  gpt-5-mini  ",
                    ),
                )
                assert generation.status_code == 201
                generation_data = generation.json()["data"]
                generation_id = UUID(generation_data["id"])
                assert generation_data["alias"] == "support-primary"
                assert generation_data["upstreamModel"] == "gpt-5-mini"
                assert generation_data["purpose"] == "generation"
                assert generation_data["providerConnectionId"] == str(ids["provider_active"])
                assert generation_data["enabled"] is True
                assert "secretRef" not in generation_data
                assert "apiKey" not in generation_data

                embedding = await client.post(
                    "/api/v1/models",
                    json=_create_payload(
                        ids["provider_active"],
                        alias="search-embedding",
                        upstream_model="text-embedding-3-small",
                        purpose="embedding",
                    ),
                )
                assert embedding.status_code == 201
                embedding_id = UUID(embedding.json()["data"]["id"])

                rerank = await client.post(
                    "/api/v1/models",
                    json=_create_payload(
                        ids["provider_active"],
                        alias="search-rerank",
                        upstream_model="rerank-safe-model",
                        purpose="rerank",
                    ),
                )
                assert rerank.status_code == 201

                duplicate = await client.post(
                    "/api/v1/models",
                    json=_create_payload(
                        ids["provider_active"],
                        alias="support-primary",
                        upstream_model="another-model",
                    ),
                )
                assert duplicate.status_code == 409
                assert duplicate.json()["error"]["code"] == "MODEL_ALIAS_CONFLICT"

                for payload in (
                    _create_payload(
                        ids["provider_active"], alias="   ", upstream_model="model"
                    ),
                    _create_payload(
                        ids["provider_active"], alias="x" * 81, upstream_model="model"
                    ),
                    _create_payload(
                        ids["provider_active"], alias="blank-upstream", upstream_model="   "
                    ),
                    _create_payload(
                        ids["provider_active"],
                        alias="long-upstream",
                        upstream_model="x" * 161,
                    ),
                    _create_payload(
                        ids["provider_active"],
                        alias="bad-purpose",
                        upstream_model="model",
                        purpose="chat",
                    ),
                ):
                    rejected = await client.post("/api/v1/models", json=payload)
                    assert rejected.status_code == 422

                unknown = await client.post(
                    "/api/v1/models",
                    json={
                        **_create_payload(
                            ids["provider_active"],
                            alias="unknown-field",
                            upstream_model="model",
                        ),
                        "baseUrl": "https://example.invalid",
                    },
                )
                assert unknown.status_code == 422

                foreign_provider = await client.post(
                    "/api/v1/models",
                    json=_create_payload(
                        ids["provider_foreign"],
                        alias="foreign-provider",
                        upstream_model="model",
                    ),
                )
                assert foreign_provider.status_code == 404
                assert foreign_provider.json()["error"]["code"] == "PROVIDER_NOT_FOUND"

                disabled_provider = await client.post(
                    "/api/v1/models",
                    json=_create_payload(
                        ids["provider_disabled"],
                        alias="disabled-provider",
                        upstream_model="model",
                    ),
                )
                assert disabled_provider.status_code == 409
                assert disabled_provider.json()["error"]["code"] == "MODEL_PROVIDER_INELIGIBLE"

                untested_provider = await client.post(
                    "/api/v1/models",
                    json=_create_payload(
                        ids["provider_untested"],
                        alias="untested-provider",
                        upstream_model="model",
                    ),
                )
                assert untested_provider.status_code == 409

                listed = await client.get("/api/v1/models")
                assert listed.status_code == 200
                listed_ids = {UUID(item["id"]) for item in listed.json()["data"]}
                assert generation_id in listed_ids
                assert embedding_id in listed_ids

                updated = await client.patch(
                    f"/api/v1/models/{generation_id}",
                    json={
                        "providerConnectionId": str(ids["provider_alt"]),
                        "upstreamModel": "  claude-haiku-safe  ",
                        "enabled": False,
                    },
                )
                assert updated.status_code == 200
                assert updated.json()["data"]["providerConnectionId"] == str(ids["provider_alt"])
                assert updated.json()["data"]["upstreamModel"] == "claude-haiku-safe"
                assert updated.json()["data"]["enabled"] is False
                assert updated.json()["data"]["alias"] == "support-primary"
                assert updated.json()["data"]["purpose"] == "generation"

                for immutable_patch in (
                    {"alias": "renamed"},
                    {"purpose": "embedding"},
                    {},
                ):
                    rejected_patch = await client.patch(
                        f"/api/v1/models/{generation_id}", json=immutable_patch
                    )
                    assert rejected_patch.status_code == 422

                ineligible_update = await client.patch(
                    f"/api/v1/models/{generation_id}",
                    json={"providerConnectionId": str(ids["provider_disabled"])},
                )
                assert ineligible_update.status_code == 409

                foreign_update = await client.patch(
                    f"/api/v1/models/{generation_id}",
                    json={"providerConnectionId": str(ids["provider_foreign"])},
                )
                assert foreign_update.status_code == 404

                # A fail-safe disable is still allowed when the provider later loses
                # active status. Re-enabling against that provider is not.
                async with session_factory() as session, session.begin():
                    await session.execute(
                        text(
                            "UPDATE provider_connections SET status='invalid' WHERE id=:id"
                        ),
                        {"id": ids["provider_alt"]},
                    )
                disabled = await client.patch(
                    f"/api/v1/models/{generation_id}", json={"enabled": False}
                )
                assert disabled.status_code == 200
                reenable = await client.patch(
                    f"/api/v1/models/{generation_id}", json={"enabled": True}
                )
                assert reenable.status_code == 409

            # The same alias is valid in another tenant and must not appear in tenant A.
            _install_overrides(
                session_factory,
                user_id=ids["foreign"],
                tenant_id=ids["tenant_b"],
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                foreign_same_alias = await client.post(
                    "/api/v1/models",
                    json=_create_payload(
                        ids["provider_foreign"],
                        alias="support-primary",
                        upstream_model="tenant-b-model",
                    ),
                )
                assert foreign_same_alias.status_code == 201
                foreign_model_id = UUID(foreign_same_alias.json()["data"]["id"])

            _install_overrides(
                session_factory,
                user_id=ids["owner"],
                tenant_id=ids["tenant_a"],
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                listed = await client.get("/api/v1/models")
                assert listed.status_code == 200
                assert str(foreign_model_id) not in {item["id"] for item in listed.json()["data"]}
                foreign_model_patch = await client.patch(
                    f"/api/v1/models/{foreign_model_id}", json={"enabled": False}
                )
                assert foreign_model_patch.status_code == 404

                reference_id = uuid4()
                async with session_factory() as session, session.begin():
                    await session.execute(
                        text(
                            """
                            INSERT INTO model_configuration_references (
                              tenant_id, model_configuration_id, reference_kind, reference_id
                            ) VALUES (
                              :tenant, :model, 'agent_version_published', :reference
                            )
                            """
                        ),
                        {
                            "tenant": ids["tenant_a"],
                            "model": generation_id,
                            "reference": reference_id,
                        },
                    )
                referenced_delete = await client.delete(f"/api/v1/models/{generation_id}")
                assert referenced_delete.status_code == 409
                assert (
                    referenced_delete.json()["error"]["code"]
                    == "MODEL_CONFIGURATION_IN_USE"
                )

                async with session_factory() as session, session.begin():
                    await session.execute(
                        text(
                            "DELETE FROM model_configuration_references WHERE reference_id=:id"
                        ),
                        {"id": reference_id},
                    )
                deleted = await client.delete(f"/api/v1/models/{generation_id}")
                assert deleted.status_code == 204
                deleted_unreferenced = await client.delete(f"/api/v1/models/{embedding_id}")
                assert deleted_unreferenced.status_code == 204

            _install_overrides(
                session_factory,
                user_id=ids["ordinary"],
                tenant_id=ids["tenant_a"],
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                remaining_model = await client.get("/api/v1/models")
                assert remaining_model.status_code == 403

                # Use the surviving rerank model for mutation authorization checks.
                _install_overrides(
                    session_factory,
                    user_id=ids["owner"],
                    tenant_id=ids["tenant_a"],
                )
                owner_list = await client.get("/api/v1/models")
                rerank_id = UUID(
                    next(
                        item["id"]
                        for item in owner_list.json()["data"]
                        if item["alias"] == "search-rerank"
                    )
                )
                _install_overrides(
                    session_factory,
                    user_id=ids["ordinary"],
                    tenant_id=ids["tenant_a"],
                )
                denied_update = await client.patch(
                    f"/api/v1/models/{rerank_id}", json={"enabled": False}
                )
                assert denied_update.status_code == 403
                denied_delete = await client.delete(f"/api/v1/models/{rerank_id}")
                assert denied_delete.status_code == 403
        finally:
            _clear_overrides()
            if ids:
                async with session_factory() as session, session.begin():
                    await _cleanup(session, ids)
            await engine.dispose()

    asyncio.run(scenario())
