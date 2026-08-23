from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping

import httpx
import pytest

from app.core.auth import WorkforceOidcValidator
from app.core.config import PlatformSettings, load_settings
from app.core.errors import AuthenticationError

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_KEYCLOAK_OIDC_INTEGRATION") != "1",
    reason="requires the real local Keycloak workforce OIDC test realm",
)

ISSUER = "http://localhost:8080/realms/serviq"
ALTERNATE_LOOPBACK_ISSUER = "http://127.0.0.1:8080/realms/serviq"
AUDIENCE = "serviq-test"
ENABLED_USERNAME = "serviq-test-user"
ENABLED_PASSWORD = "serviq-test-password-placeholder"
DISABLED_USERNAME = "serviq-disabled-user"
DISABLED_PASSWORD = "serviq-disabled-password-placeholder"
EXPECTED_SUBJECT = "11111111-1111-4111-8111-111111111111"
HTTP_TIMEOUT_SECONDS = 5.0


def _request_token(
    *,
    username: str,
    password: str,
    issuer: str = ISSUER,
) -> httpx.Response:
    return httpx.post(
        f"{issuer}/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": AUDIENCE,
            "username": username,
            "password": password,
        },
        headers={"Accept": "application/json"},
        timeout=HTTP_TIMEOUT_SECONDS,
        follow_redirects=False,
    )


def _access_token(*, issuer: str = ISSUER) -> str:
    response = _request_token(
        username=ENABLED_USERNAME,
        password=ENABLED_PASSWORD,
        issuer=issuer,
    )
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, Mapping)
    raw_token = payload.get("access_token")
    assert isinstance(raw_token, str) and raw_token
    return raw_token


def _settings() -> PlatformSettings:
    settings = load_settings()
    assert str(settings.oidc_issuer_url).rstrip("/") == ISSUER
    assert settings.oidc_client_id == AUDIENCE
    return settings


def test_real_keycloak_token_validates_through_live_discovery_and_jwks() -> None:
    identity = asyncio.run(WorkforceOidcValidator(_settings()).validate(_access_token()))

    assert identity.issuer == ISSUER
    assert identity.subject == EXPECTED_SUBJECT
    assert "tenant_id" not in type(identity).model_fields
    assert "permissions" not in type(identity).model_fields


def test_real_keycloak_token_with_wrong_audience_fails_closed() -> None:
    settings = _settings().model_copy(update={"oidc_client_id": "wrong-audience"})

    with pytest.raises(AuthenticationError) as exc_info:
        asyncio.run(WorkforceOidcValidator(settings).validate(_access_token()))

    assert exc_info.value.error_code == "UNAUTHENTICATED"
    assert str(exc_info.value) == "Authentication failed."


def test_real_keycloak_token_with_wrong_issuer_fails_closed() -> None:
    raw_token = _access_token(issuer=ALTERNATE_LOOPBACK_ISSUER)

    with pytest.raises(AuthenticationError) as exc_info:
        asyncio.run(WorkforceOidcValidator(_settings()).validate(raw_token))

    assert exc_info.value.error_code == "UNAUTHENTICATED"
    assert str(exc_info.value) == "Authentication failed."


@pytest.mark.parametrize(
    ("username", "password"),
    [
        (DISABLED_USERNAME, DISABLED_PASSWORD),
        ("serviq-unknown-user", "serviq-unknown-password-placeholder"),
    ],
)
def test_disabled_or_unknown_subject_cannot_obtain_token(
    username: str,
    password: str,
) -> None:
    response = _request_token(username=username, password=password)

    assert response.status_code == 401
    payload = response.json()
    assert isinstance(payload, Mapping)
    assert payload.get("error") == "invalid_grant"
    assert "access_token" not in payload
    assert "refresh_token" not in payload


def test_raw_token_is_absent_from_captured_logs_and_safe_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw_token = _access_token()
    settings = _settings().model_copy(update={"oidc_client_id": "wrong-audience"})

    with pytest.raises(AuthenticationError) as exc_info:
        asyncio.run(WorkforceOidcValidator(settings).validate(raw_token))

    assert raw_token not in caplog.text
    assert raw_token not in str(exc_info.value)
