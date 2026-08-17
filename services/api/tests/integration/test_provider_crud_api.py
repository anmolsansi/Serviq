from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import load_settings
from app.core.database import (
    create_database_engine,
    create_database_session_factory,
    get_database_session,
)
from app.core.principal import require_tenant_id, require_workforce_user_id
from app.core.secret_store import LocalEncryptedSecretStore, SecretNotFoundError
from app.main import app
from app.modules.providers.router import get_provider_secret_store

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)

KEY_ONE = "sk-fake-provider-one-never-real"
KEY_TWO = "sk-fake-provider-two-never-real"
KEY_THREE = "sk-fake-provider-three-never-real"


def _install_overrides(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: UUID,
    tenant_id: UUID,
    secret_store: LocalEncryptedSecretStore,
) -> None:
    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_database_session] = override_session
    app.dependency_overrides[require_workforce_user_id] = lambda: user_id
    app.dependency_overrides[require_tenant_id] = lambda: tenant_id
    app.dependency_overrides[get_provider_secret_store] = lambda: secret_store


def _clear_overrides() -> None:
    for dependency in (
        get_database_session,
        require_workforce_user_id,
        require_tenant_id,
        get_provider_secret_store,
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
    ids = {name: uuid4() for name in ("tenant_a", "tenant_b", "owner", "ordinary", "foreign")}
    owner_role = await _global_role_id(session, "owner")
    ordinary_role = uuid4()
    ids["ordinary_role"] = ordinary_role

    await session.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, status, default_locale)
            VALUES (:tenant_a, :slug_a, 'Provider Team', 'active', 'en'),
                   (:tenant_b, :slug_b, 'Provider Team', 'active', 'en')
            """
        ),
        {
            **ids,
            "slug_a": f"provider-crud-a-{ids['tenant_a'].hex[:10]}",
            "slug_b": f"provider-crud-b-{ids['tenant_b'].hex[:10]}",
        },
    )
    for key in ("owner", "ordinary", "foreign"):
        await session.execute(
            text(
                """
                INSERT INTO users (
                  id, oidc_issuer, oidc_subject, email, display_name, status
                ) VALUES (
                  :id, 'https://ope291.test', :subject, :email, :name, 'active'
                )
                """
            ),
            {
                "id": ids[key],
                "subject": f"{key}-{ids[key].hex}",
                "email": f"{key}@example.com",
                "name": key.title(),
            },
        )
    await session.execute(
        text(
            """
            INSERT INTO roles (id, tenant_id, key, display_name, is_system)
            VALUES (:id, :tenant, :key, 'Ordinary Agent', false)
            """
        ),
        {
            "id": ordinary_role,
            "tenant": ids["tenant_a"],
            "key": f"ordinary-{ordinary_role.hex}",
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
    return ids


async def _cleanup(session: AsyncSession, ids: dict[str, UUID]) -> None:
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


def _record_count(path: Path) -> int:
    if not path.exists():
        return 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    return len(payload["records"])


def test_provider_crud_secret_safety_compensation_and_tenant_isolation(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        secret_path = tmp_path / "provider-secrets.json"
        secret_store = LocalEncryptedSecretStore(
            bootstrap_secret=SecretStr("ope291-bootstrap-key-for-tests"),
            path=secret_path,
        )
        transport = httpx.ASGITransport(app=app)
        ids: dict[str, UUID] = {}
        try:
            async with session_factory() as session, session.begin():
                ids = await _seed(session)

            _install_overrides(
                session_factory,
                user_id=ids["owner"],
                tenant_id=ids["tenant_a"],
                secret_store=secret_store,
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                created = await client.post(
                    "/api/v1/providers",
                    json={
                        "provider": "openai",
                        "displayName": "Primary OpenAI",
                        "apiKey": KEY_ONE,
                    },
                )
                assert created.status_code == 201
                provider_id = UUID(created.json()["data"]["id"])
                assert created.json()["data"]["status"] == "untested"
                assert KEY_ONE not in created.text
                assert "apiKey" not in created.json()["data"]
                assert "secretRef" not in created.json()["data"]

                async with session_factory() as session:
                    secret_ref = await session.scalar(
                        text(
                            """
                            SELECT secret_ref FROM provider_connections
                            WHERE id=:id AND tenant_id=:tenant
                            """
                        ),
                        {"id": provider_id, "tenant": ids["tenant_a"]},
                    )
                    assert isinstance(secret_ref, str)
                    assert KEY_ONE not in secret_ref
                    assert secret_store.get_secret(
                        ids["tenant_a"], secret_ref
                    ).get_secret_value() == KEY_ONE

                persisted = secret_path.read_text(encoding="utf-8")
                assert KEY_ONE not in persisted

                # A second tenant can have the same display name without colliding.
                foreign_secret_ref = secret_store.put_secret(
                    ids["tenant_b"], SecretStr("sk-fake-foreign")
                )
                foreign_provider_id = uuid4()
                async with session_factory() as session, session.begin():
                    await session.execute(
                        text(
                            """
                            INSERT INTO provider_connections (
                              id, tenant_id, provider, display_name, secret_ref,
                              status, created_by
                            ) VALUES (
                              :id, :tenant, 'anthropic', 'Primary OpenAI',
                              :secret_ref, 'untested', :created_by
                            )
                            """
                        ),
                        {
                            "id": foreign_provider_id,
                            "tenant": ids["tenant_b"],
                            "secret_ref": foreign_secret_ref,
                            "created_by": ids["foreign"],
                        },
                    )

                listed = await client.get("/api/v1/providers")
                assert listed.status_code == 200
                assert [item["id"] for item in listed.json()["data"]] == [str(provider_id)]
                foreign_detail = await client.get(f"/api/v1/providers/{foreign_provider_id}")
                assert foreign_detail.status_code == 404

                same_ref_update = await client.patch(
                    f"/api/v1/providers/{provider_id}",
                    json={"displayName": "OpenAI Main"},
                )
                assert same_ref_update.status_code == 200
                async with session_factory() as session:
                    unchanged_ref = await session.scalar(
                        text("SELECT secret_ref FROM provider_connections WHERE id=:id"),
                        {"id": provider_id},
                    )
                assert unchanged_ref == secret_ref

                second = await client.post(
                    "/api/v1/providers",
                    json={
                        "provider": "anthropic",
                        "displayName": "Secondary",
                        "apiKey": KEY_TWO,
                    },
                )
                assert second.status_code == 201
                before_duplicate_records = _record_count(secret_path)
                duplicate = await client.post(
                    "/api/v1/providers",
                    json={
                        "provider": "gemini",
                        "displayName": "Secondary",
                        "apiKey": KEY_THREE,
                    },
                )
                assert duplicate.status_code == 409
                assert _record_count(secret_path) == before_duplicate_records

                replacement_conflict = await client.patch(
                    f"/api/v1/providers/{provider_id}",
                    json={"displayName": "Secondary", "apiKey": KEY_THREE},
                )
                assert replacement_conflict.status_code == 409
                assert _record_count(secret_path) == before_duplicate_records
                assert secret_store.get_secret(
                    ids["tenant_a"], secret_ref
                ).get_secret_value() == KEY_ONE

                replacement = await client.patch(
                    f"/api/v1/providers/{provider_id}",
                    json={"apiKey": KEY_THREE},
                )
                assert replacement.status_code == 200
                assert replacement.json()["data"]["status"] == "untested"
                async with session_factory() as session:
                    replacement_ref = await session.scalar(
                        text("SELECT secret_ref FROM provider_connections WHERE id=:id"),
                        {"id": provider_id},
                    )
                assert isinstance(replacement_ref, str)
                assert replacement_ref != secret_ref
                assert secret_store.get_secret(
                    ids["tenant_a"], replacement_ref
                ).get_secret_value() == KEY_THREE
                with pytest.raises(SecretNotFoundError):
                    secret_store.get_secret(ids["tenant_a"], secret_ref)

                model_id = uuid4()
                async with session_factory() as session, session.begin():
                    await session.execute(
                        text(
                            """
                            INSERT INTO model_configurations (
                              id, tenant_id, provider_connection_id, alias,
                              upstream_model, purpose, enabled
                            ) VALUES (
                              :id, :tenant, :provider, 'delete-guard',
                              'fake-model', 'generation', true
                            )
                            """
                        ),
                        {
                            "id": model_id,
                            "tenant": ids["tenant_a"],
                            "provider": provider_id,
                        },
                    )
                referenced = await client.delete(f"/api/v1/providers/{provider_id}")
                assert referenced.status_code == 409
                async with session_factory() as session, session.begin():
                    await session.execute(
                        text("DELETE FROM model_configurations WHERE id=:id"),
                        {"id": model_id},
                    )
                deleted = await client.delete(f"/api/v1/providers/{provider_id}")
                assert deleted.status_code == 204
                with pytest.raises(SecretNotFoundError):
                    secret_store.get_secret(ids["tenant_a"], replacement_ref)

            _install_overrides(
                session_factory,
                user_id=ids["ordinary"],
                tenant_id=ids["tenant_a"],
                secret_store=secret_store,
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                denied = await client.post(
                    "/api/v1/providers",
                    json={
                        "provider": "openrouter",
                        "displayName": "Denied",
                        "apiKey": KEY_ONE,
                    },
                )
                assert denied.status_code == 403

            for secret in (KEY_ONE, KEY_TWO, KEY_THREE):
                assert secret not in caplog.text
        finally:
            _clear_overrides()
            if ids:
                async with session_factory() as session, session.begin():
                    await _cleanup(session, ids)
            await engine.dispose()

    asyncio.run(scenario())
