from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable
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
from app.core.rate_limits import RateLimitDecision, RateLimitUnavailableError
from app.core.secret_store import LocalEncryptedSecretStore
from app.main import app
from app.modules.providers.gateway import ProviderConnectivityOutcome
from app.modules.providers.router import (
    get_provider_connectivity_gateway,
    get_provider_connectivity_rate_limiter,
    get_provider_secret_store,
)

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)

KEY = "sk-ope298-fake-key-never-real"
RAW_PROVIDER_DETAIL = "RAW-UPSTREAM-DETAIL-MUST-NEVER-LEAK"


class FakeGateway:
    def __init__(self) -> None:
        self.outcome = ProviderConnectivityOutcome(ok=True)
        self.calls: list[dict[str, object]] = []
        self.before_return: Callable[[], Awaitable[None]] | None = None

    async def test(
        self,
        *,
        tenant_id: UUID,
        provider: str,
        api_key: SecretStr,
        correlation_id: str,
    ) -> ProviderConnectivityOutcome:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "provider": provider,
                "api_key": api_key.get_secret_value(),
                "correlation_id": correlation_id,
            }
        )
        if self.before_return is not None:
            await self.before_return()
            self.before_return = None
        return self.outcome


class FakeRateLimiter:
    def __init__(self) -> None:
        self.decision = RateLimitDecision(allowed=True)
        self.unavailable = False
        self.calls = 0

    async def check_and_consume(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        provider_connection_id: UUID,
    ) -> RateLimitDecision:
        del tenant_id, user_id, provider_connection_id
        self.calls += 1
        if self.unavailable:
            raise RateLimitUnavailableError
        return self.decision


def _install_overrides(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: UUID,
    tenant_id: UUID,
    secret_store: LocalEncryptedSecretStore,
    gateway: FakeGateway,
    rate_limiter: FakeRateLimiter,
) -> None:
    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_database_session] = override_session
    app.dependency_overrides[require_workforce_user_id] = lambda: user_id
    app.dependency_overrides[require_tenant_id] = lambda: tenant_id
    app.dependency_overrides[get_provider_secret_store] = lambda: secret_store
    app.dependency_overrides[get_provider_connectivity_gateway] = lambda: gateway
    app.dependency_overrides[get_provider_connectivity_rate_limiter] = lambda: rate_limiter


def _clear_overrides() -> None:
    for dependency in (
        get_database_session,
        require_workforce_user_id,
        require_tenant_id,
        get_provider_secret_store,
        get_provider_connectivity_gateway,
        get_provider_connectivity_rate_limiter,
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
    ids = {
        name: uuid4()
        for name in (
            "tenant_a",
            "tenant_b",
            "owner",
            "ordinary",
            "foreign",
            "provider",
            "foreign_provider",
        )
    }
    owner_role = await _global_role_id(session, "owner")
    ordinary_role = uuid4()
    ids["ordinary_role"] = ordinary_role

    await session.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, status, default_locale)
            VALUES (:tenant_a, :slug_a, 'Connectivity A', 'active', 'en'),
                   (:tenant_b, :slug_b, 'Connectivity B', 'active', 'en')
            """
        ),
        {
            **ids,
            "slug_a": f"ope298-a-{ids['tenant_a'].hex[:10]}",
            "slug_b": f"ope298-b-{ids['tenant_b'].hex[:10]}",
        },
    )
    for key in ("owner", "ordinary", "foreign"):
        await session.execute(
            text(
                """
                INSERT INTO users (id, oidc_issuer, oidc_subject, email, display_name, status)
                VALUES (:id, 'https://ope298.test', :subject, :email, :name, 'active')
                """
            ),
            {
                "id": ids[key],
                "subject": f"{key}-{ids[key].hex}",
                "email": f"ope298-{key}@example.com",
                "name": key.title(),
            },
        )
    await session.execute(
        text(
            """
            INSERT INTO roles (id, tenant_id, key, display_name, is_system)
            VALUES (:id, :tenant, :key, 'No Provider Permission', false)
            """
        ),
        {
            "id": ordinary_role,
            "tenant": ids["tenant_a"],
            "key": f"ope298-ordinary-{ordinary_role.hex}",
        },
    )
    ids.update(
        {
            "owner_membership": uuid4(),
            "ordinary_membership": uuid4(),
            "foreign_membership": uuid4(),
        }
    )
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
    await session.execute(text("DELETE FROM users WHERE id IN (:owner, :ordinary, :foreign)"), ids)
    await session.execute(
        text("DELETE FROM tenants WHERE id IN (:a, :b)"),
        {"a": ids["tenant_a"], "b": ids["tenant_b"]},
    )


async def _set_status(
    session_factory: async_sessionmaker[AsyncSession],
    provider_id: UUID,
    *,
    status_value: str,
) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                """
                UPDATE provider_connections
                SET status=:status, last_tested_at=NULL, last_error_code=NULL
                WHERE id=:id
                """
            ),
            {"status": status_value, "id": provider_id},
        )


async def _metadata(
    session_factory: async_sessionmaker[AsyncSession],
    provider_id: UUID,
) -> tuple[str, object, str | None]:
    async with session_factory() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT status, last_tested_at, last_error_code
                    FROM provider_connections WHERE id=:id
                    """
                ),
                {"id": provider_id},
            )
        ).one()
    return str(row.status), row.last_tested_at, row.last_error_code


def test_provider_connectivity_route_persistence_security_and_isolation(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        secret_path = tmp_path / "ope298-provider-secrets.json"
        secret_store = LocalEncryptedSecretStore(
            bootstrap_secret=SecretStr("ope298-bootstrap-secret-for-tests"),
            path=secret_path,
        )
        gateway = FakeGateway()
        limiter = FakeRateLimiter()
        transport = httpx.ASGITransport(app=app)
        ids: dict[str, UUID] = {}
        secret_refs: list[str] = []
        try:
            async with session_factory() as session, session.begin():
                ids = await _seed(session)

            secret_ref = secret_store.put_secret(ids["tenant_a"], SecretStr(KEY))
            foreign_secret_ref = secret_store.put_secret(
                ids["tenant_b"], SecretStr("sk-foreign-never-real")
            )
            secret_refs.extend([secret_ref, foreign_secret_ref])
            async with session_factory() as session, session.begin():
                await session.execute(
                    text(
                        """
                        INSERT INTO provider_connections (
                          id, tenant_id, provider, display_name, secret_ref, status, created_by
                        ) VALUES
                          (:provider, :tenant_a, 'openai', 'OPE 298 Provider', :secret_ref,
                           'untested', :owner),
                          (:foreign_provider, :tenant_b, 'anthropic', 'Foreign Provider',
                           :foreign_secret_ref, 'untested', :foreign)
                        """
                    ),
                    {
                        **ids,
                        "secret_ref": secret_ref,
                        "foreign_secret_ref": foreign_secret_ref,
                    },
                )

            _install_overrides(
                session_factory,
                user_id=ids["owner"],
                tenant_id=ids["tenant_a"],
                secret_store=secret_store,
                gateway=gateway,
                rate_limiter=limiter,
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                success = await client.post(f"/api/v1/providers/{ids['provider']}/test")
                assert success.status_code == 200
                assert success.json()["data"] == {"status": "active", "errorCode": None}
                status_value, tested_at, error_code = await _metadata(
                    session_factory, ids["provider"]
                )
                assert status_value == "active"
                assert tested_at is not None
                assert error_code is None
                assert gateway.calls[-1]["provider"] == "openai"
                assert gateway.calls[-1]["api_key"] == KEY
                assert KEY not in success.text

                # Authentication failure is the only provider failure that invalidates
                # an enabled credential.
                gateway.outcome = ProviderConnectivityOutcome(
                    ok=False, error_code="PROVIDER_AUTH_FAILED"
                )
                auth_failure = await client.post(f"/api/v1/providers/{ids['provider']}/test")
                assert auth_failure.status_code == 200
                assert auth_failure.json()["data"] == {
                    "status": "invalid",
                    "errorCode": "PROVIDER_AUTH_FAILED",
                }
                status_value, tested_at, error_code = await _metadata(
                    session_factory, ids["provider"]
                )
                assert status_value == "invalid"
                assert tested_at is not None
                assert error_code == "PROVIDER_AUTH_FAILED"

                # Temporary/configuration failures preserve the existing active status.
                for code in (
                    "PROVIDER_RATE_LIMITED",
                    "PROVIDER_TIMEOUT",
                    "PROVIDER_UNAVAILABLE",
                    "PROVIDER_INVALID_REQUEST",
                ):
                    await _set_status(session_factory, ids["provider"], status_value="active")
                    gateway.outcome = ProviderConnectivityOutcome(
                        ok=False,
                        error_code=code,
                    )
                    transient = await client.post(f"/api/v1/providers/{ids['provider']}/test")
                    assert transient.status_code == 200
                    assert transient.json()["data"] == {"status": "active", "errorCode": code}
                    status_value, tested_at, error_code = await _metadata(
                        session_factory, ids["provider"]
                    )
                    assert status_value == "active"
                    assert tested_at is not None
                    assert error_code == code
                    assert RAW_PROVIDER_DETAIL not in transient.text

                # Public callers cannot smuggle model, prompt, URL, or any other body.
                calls_before_body = len(gateway.calls)
                arbitrary = await client.post(
                    f"/api/v1/providers/{ids['provider']}/test",
                    json={
                        "model": "attacker/model",
                        "prompt": "do something else",
                        "baseUrl": "https://attacker.invalid",
                    },
                )
                assert arbitrary.status_code == 422
                assert len(gateway.calls) == calls_before_body

                # Serviq's route limiter prevents the external provider call entirely.
                limiter.decision = RateLimitDecision(allowed=False, retry_after_seconds=37)
                calls_before_limit = len(gateway.calls)
                limited = await client.post(f"/api/v1/providers/{ids['provider']}/test")
                assert limited.status_code == 429
                assert limited.headers["retry-after"] == "37"
                assert limited.json()["error"]["code"] == "PROVIDER_TEST_RATE_LIMITED"
                assert len(gateway.calls) == calls_before_limit

                # If shared rate-limit state is unavailable, fail closed.
                limiter.decision = RateLimitDecision(allowed=True)
                limiter.unavailable = True
                unavailable = await client.post(f"/api/v1/providers/{ids['provider']}/test")
                assert unavailable.status_code == 503
                assert unavailable.json()["error"]["code"] == "PROVIDER_TEST_UNAVAILABLE"
                assert len(gateway.calls) == calls_before_limit
                limiter.unavailable = False

                # Disabled connections are not charged/rate-limited/resolved/invoked.
                await _set_status(session_factory, ids["provider"], status_value="disabled")
                calls_before_disabled = len(gateway.calls)
                limiter_calls_before_disabled = limiter.calls
                disabled = await client.post(f"/api/v1/providers/{ids['provider']}/test")
                assert disabled.status_code == 200
                assert disabled.json()["data"] == {"status": "disabled", "errorCode": None}
                assert len(gateway.calls) == calls_before_disabled
                assert limiter.calls == limiter_calls_before_disabled

                # Restore enabled status and simulate a key rotation while the provider
                # call is in flight. The old result must not stamp the replacement key.
                await _set_status(session_factory, ids["provider"], status_value="untested")
                new_ref = secret_store.put_secret(
                    ids["tenant_a"], SecretStr("sk-rotated-never-real")
                )
                secret_refs.append(new_ref)

                async def rotate_during_call() -> None:
                    async with session_factory() as separate, separate.begin():
                        await separate.execute(
                            text(
                                """
                                UPDATE provider_connections
                                SET secret_ref=:new_ref, status='untested',
                                    last_tested_at=NULL, last_error_code=NULL
                                WHERE id=:id
                                """
                            ),
                            {"new_ref": new_ref, "id": ids["provider"]},
                        )

                gateway.outcome = ProviderConnectivityOutcome(ok=True)
                gateway.before_return = rotate_during_call
                stale = await client.post(f"/api/v1/providers/{ids['provider']}/test")
                assert stale.status_code == 409
                assert stale.json()["error"]["code"] == "PROVIDER_TEST_STALE"
                status_value, tested_at, error_code = await _metadata(
                    session_factory, ids["provider"]
                )
                assert status_value == "untested"
                assert tested_at is None
                assert error_code is None

                # A provider owned by another tenant is indistinguishable from absent.
                foreign = await client.post(
                    f"/api/v1/providers/{ids['foreign_provider']}/test"
                )
                assert foreign.status_code == 404
                assert foreign.json()["error"]["code"] == "PROVIDER_NOT_FOUND"

            # Same tenant, active membership, but no provider-management permission.
            _install_overrides(
                session_factory,
                user_id=ids["ordinary"],
                tenant_id=ids["tenant_a"],
                secret_store=secret_store,
                gateway=gateway,
                rate_limiter=limiter,
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                calls_before_forbidden = len(gateway.calls)
                forbidden = await client.post(f"/api/v1/providers/{ids['provider']}/test")
                assert forbidden.status_code == 403
                assert forbidden.json()["error"]["code"] == "FORBIDDEN"
                assert len(gateway.calls) == calls_before_forbidden

            # Persistence and captured logs contain no plaintext credential or fake raw
            # provider detail. Secret file is encrypted by the existing adapter.
            persisted_secret_file = secret_path.read_text(encoding="utf-8")
            assert KEY not in persisted_secret_file
            assert KEY not in caplog.text
            assert RAW_PROVIDER_DETAIL not in caplog.text
            async with session_factory() as session:
                stored_codes = (
                    await session.execute(
                        text(
                            "SELECT last_error_code FROM provider_connections "
                            "WHERE tenant_id=:tenant"
                        ),
                        {"tenant": ids["tenant_a"]},
                    )
                ).scalars().all()
            assert all(
                code is None or RAW_PROVIDER_DETAIL not in str(code)
                for code in stored_codes
            )
        finally:
            _clear_overrides()
            if ids:
                async with session_factory() as session, session.begin():
                    await _cleanup(session, ids)
            # The cleanup deletes metadata first. Secret-store test material lives only
            # under pytest tmp_path and is discarded with the test directory.
            await engine.dispose()

    asyncio.run(scenario())
