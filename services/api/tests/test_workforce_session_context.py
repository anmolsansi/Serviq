from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import cast
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import app.modules.auth.router as auth_router_module
import app.modules.organizations.router as organizations_router_module
import app.modules.providers.router as providers_router_module
from app.core.config import PlatformSettings, load_settings
from app.core.database import get_database_session
from app.core.errors import AuthenticationError
from app.core.session import SessionUnavailableError, WorkforceSessionData
from app.main import app
from app.modules.auth.router import _validate_frontend_redirect_uri
from app.modules.tenancy.errors import TenantMembershipAccessError
from app.modules.tenancy.schemas import ResolvedTenantMembership


class FakeSessionStore:
    def __init__(self, sessions: dict[str, WorkforceSessionData] | None = None) -> None:
        self.sessions = sessions or {}
        self.fail_reads = False

    async def get_session(self, session_id: str) -> WorkforceSessionData | None:
        if self.fail_reads:
            raise SessionUnavailableError
        return self.sessions.get(session_id)

    async def replace_session(self, session_id: str, data: WorkforceSessionData) -> None:
        if session_id not in self.sessions:
            raise AuthenticationError
        self.sessions[session_id] = data

    async def destroy_session(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)


def _settings() -> PlatformSettings:
    return PlatformSettings.model_validate(
        {
            "SERVIQ_ENV": "test",
            "SERVIQ_PUBLIC_BASE_URL": "http://localhost:3000",
            "SERVIQ_API_BASE_URL": "http://localhost:8000",
            "DATABASE_URL": "postgresql://serviq:serviq@localhost:5432/serviq",
            "VALKEY_URL": "valkey://localhost:6379/0",
            "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
            "OBJECT_STORAGE_ENDPOINT": "http://localhost:8333",
            "OBJECT_STORAGE_BUCKET": "serviq-test",
            "OBJECT_STORAGE_ACCESS_KEY": "test-placeholder",
            "OBJECT_STORAGE_SECRET_KEY": "test-placeholder",
            "OIDC_ISSUER_URL": "http://localhost:8080/realms/serviq",
            "OIDC_CLIENT_ID": "serviq-test",
            "OIDC_CLIENT_SECRET": "test-placeholder",
            "OIDC_REDIRECT_URI": "http://localhost:3000/auth/callback",
            "SESSION_SECRET": "test-placeholder",
            "LLM_GATEWAY_URL": "http://localhost:8100",
            "LLM_GATEWAY_INTERNAL_TOKEN": "test-placeholder",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
            "LOG_LEVEL": "INFO",
        }
    )


def _session(
    user_id: UUID,
    *,
    tenant_id: UUID | None,
    csrf_token: str = "csrf-token-with-at-least-thirty-two-bytes",
) -> WorkforceSessionData:
    return WorkforceSessionData(
        user_id=user_id,
        oidc_subject=f"subject-{user_id}",
        oidc_issuer="http://localhost:8080/realms/serviq",
        email="user@example.com",
        email_verified=True,
        display_name="Session User",
        active_tenant_id=tenant_id,
        csrf_token=csrf_token,
    )


def _install_database_override() -> None:
    async def override_database_session() -> AsyncIterator[AsyncSession]:
        yield cast(AsyncSession, object())

    app.dependency_overrides[get_database_session] = override_database_session


def _reset_app_state() -> None:
    app.dependency_overrides.pop(get_database_session, None)
    app.dependency_overrides.pop(load_settings, None)
    if hasattr(app.state, "session_store"):
        del app.state.session_store


def test_session_context_tenant_switch_and_csrf_use_server_owned_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        user_id = uuid4()
        tenant_a = uuid4()
        tenant_b = uuid4()
        session_id = "opaque-session-id"
        csrf_token = "csrf-token-with-at-least-thirty-two-bytes"
        store = FakeSessionStore(
            {session_id: _session(user_id, tenant_id=tenant_a, csrf_token=csrf_token)}
        )
        captured_tenants: list[UUID] = []

        async def fake_list_organizations(
            _session: AsyncSession,
            *,
            user_id: UUID,
        ) -> tuple[object, ...]:
            assert user_id == expected_user_id
            return ()

        async def fake_list_providers(
            _session: AsyncSession,
            *,
            user_id: UUID,
            tenant_id: UUID,
        ) -> tuple[object, ...]:
            assert user_id == expected_user_id
            captured_tenants.append(tenant_id)
            return ()

        async def fake_resolve_membership(
            _session: AsyncSession,
            *,
            user_id: UUID,
            tenant_id: UUID,
        ) -> ResolvedTenantMembership:
            assert user_id == expected_user_id
            assert tenant_id == tenant_b
            return ResolvedTenantMembership(
                membership_id=uuid4(),
                tenant_id=tenant_id,
                user_id=user_id,
                status="active",
                permissions=(),
            )

        expected_user_id = user_id
        monkeypatch.setattr(
            organizations_router_module,
            "list_organizations",
            fake_list_organizations,
        )
        monkeypatch.setattr(providers_router_module, "list_providers", fake_list_providers)
        monkeypatch.setattr(
            auth_router_module,
            "resolve_tenant_membership",
            fake_resolve_membership,
        )
        app.state.session_store = store
        app.dependency_overrides[load_settings] = _settings
        _install_database_override()

        transport = httpx.ASGITransport(app=app)
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                client.cookies.set("serviq_session", session_id)

                organizations = await client.get("/api/v1/organizations")
                assert organizations.status_code == 200

                providers = await client.get(
                    "/api/v1/providers",
                    headers={"X-Serviq-Tenant-ID": str(tenant_b)},
                )
                assert providers.status_code == 200
                assert captured_tenants == [tenant_a]

                current = await client.get("/auth/session")
                assert current.status_code == 200
                current_body = current.json()["data"]
                assert current_body["userId"] == str(user_id)
                assert current_body["activeTenantId"] == str(tenant_a)
                assert current_body["csrfToken"] == csrf_token
                assert session_id not in current.text

                missing_csrf = await client.post(
                    "/auth/tenant",
                    json={"tenantId": str(tenant_b)},
                )
                assert missing_csrf.status_code == 403
                assert missing_csrf.json()["error"]["code"] == "CSRF_VALIDATION_FAILED"

                switched = await client.post(
                    "/auth/tenant",
                    json={"tenantId": str(tenant_b)},
                    headers={"X-Serviq-CSRF-Token": csrf_token},
                )
                assert switched.status_code == 200
                assert switched.json()["data"]["activeTenantId"] == str(tenant_b)
                assert store.sessions[session_id].active_tenant_id == tenant_b

                providers_after_switch = await client.get(
                    "/api/v1/providers",
                    headers={"X-Serviq-Tenant-ID": str(tenant_a)},
                )
                assert providers_after_switch.status_code == 200
                assert captured_tenants == [tenant_a, tenant_b]

                logout_without_csrf = await client.post("/auth/logout")
                assert logout_without_csrf.status_code == 403
                assert session_id in store.sessions

                logged_out = await client.post(
                    "/auth/logout",
                    headers={"X-Serviq-CSRF-Token": csrf_token},
                )
                assert logged_out.status_code == 204
                assert session_id not in store.sessions
        finally:
            _reset_app_state()

    asyncio.run(scenario())


def test_missing_expired_and_unavailable_sessions_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        async def fake_list_organizations(
            _session: AsyncSession,
            *,
            user_id: UUID,
        ) -> tuple[object, ...]:
            raise AssertionError(f"unauthenticated request reached service: {user_id}")

        monkeypatch.setattr(
            organizations_router_module,
            "list_organizations",
            fake_list_organizations,
        )
        store = FakeSessionStore()
        app.state.session_store = store
        _install_database_override()
        transport = httpx.ASGITransport(app=app)

        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                missing = await client.get("/api/v1/organizations")
                assert missing.status_code == 401
                assert missing.json()["error"]["code"] == "UNAUTHENTICATED"

                client.cookies.set("serviq_session", "expired-session")
                expired = await client.get("/api/v1/organizations")
                assert expired.status_code == 401

                store.fail_reads = True
                unavailable = await client.get("/api/v1/organizations")
                assert unavailable.status_code == 503
                assert unavailable.json()["error"]["code"] == "SESSION_STORE_UNAVAILABLE"
                assert unavailable.headers["Retry-After"] == "5"
                assert "expired-session" not in unavailable.text
        finally:
            _reset_app_state()

    asyncio.run(scenario())


def test_foreign_tenant_cannot_become_active_context(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        user_id = uuid4()
        tenant_a = uuid4()
        foreign_tenant = uuid4()
        session_id = "opaque-session-id"
        csrf_token = "csrf-token-with-at-least-thirty-two-bytes"
        store = FakeSessionStore(
            {session_id: _session(user_id, tenant_id=tenant_a, csrf_token=csrf_token)}
        )

        async def reject_membership(
            _session: AsyncSession,
            *,
            user_id: UUID,
            tenant_id: UUID,
        ) -> ResolvedTenantMembership:
            raise TenantMembershipAccessError

        monkeypatch.setattr(
            auth_router_module,
            "resolve_tenant_membership",
            reject_membership,
        )
        app.state.session_store = store
        _install_database_override()
        transport = httpx.ASGITransport(app=app)

        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                client.cookies.set("serviq_session", session_id)
                response = await client.post(
                    "/auth/tenant",
                    json={"tenantId": str(foreign_tenant)},
                    headers={"X-Serviq-CSRF-Token": csrf_token},
                )
                assert response.status_code == 403
                assert response.json()["error"]["code"] == "TENANT_MEMBERSHIP_REQUIRED"
                assert store.sessions[session_id].active_tenant_id == tenant_a
        finally:
            _reset_app_state()

    asyncio.run(scenario())


def test_frontend_redirect_validation_uses_exact_origin() -> None:
    settings = _settings()

    assert (
        _validate_frontend_redirect_uri("http://localhost:3000/settings?tab=auth", settings)
        == "http://localhost:3000/settings?tab=auth"
    )

    for unsafe in (
        "http://localhost:3000.evil.example/settings",
        "http://localhost:3001/settings",
        "http://user@localhost:3000/settings",
        "http://localhost:3000/settings#fragment",
        "javascript:alert(1)",
    ):
        with pytest.raises(AuthenticationError):
            _validate_frontend_redirect_uri(unsafe, settings)
