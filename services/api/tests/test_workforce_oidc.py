import asyncio
import time
from collections.abc import Callable
from typing import Any

import pytest
from joserfc import jwt
from joserfc.jwk import RSAKey

from app.core.auth import OidcMetadataCache, WorkforceOidcValidator
from app.core.config import PlatformSettings
from app.core.errors import AuthenticationError

ISSUER = "http://localhost:8080/realms/serviq"
AUDIENCE = "serviq-test"
JWKS_URI = "http://localhost:8080/realms/serviq/protocol/openid-connect/certs"


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
            "OBJECT_STORAGE_ACCESS_KEY": "placeholder",
            "OBJECT_STORAGE_SECRET_KEY": "placeholder",
            "OIDC_ISSUER_URL": ISSUER,
            "OIDC_CLIENT_ID": AUDIENCE,
            "OIDC_CLIENT_SECRET": "placeholder",
            "OIDC_REDIRECT_URI": "http://localhost:3000/auth/callback",
            "SESSION_SECRET": "placeholder",
            "LLM_GATEWAY_URL": "http://localhost:8100",
            "LLM_GATEWAY_INTERNAL_TOKEN": "placeholder",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
            "LOG_LEVEL": "INFO",
            "SERVIQ_LOCAL_WEBHOOK_ALLOWLIST": "",
        }
    )


def _rsa_key(*, kid: str = "test-key") -> RSAKey:
    return RSAKey.generate_key(2048, {"kid": kid, "use": "sig", "alg": "RS256"})


def _claims(**overrides: Any) -> dict[str, Any]:
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
        "sub": "workforce-user-123",
        "email": " User@Example.COM ",
        "email_verified": True,
        "name": " Test User ",
        "tenant_id": "must-not-be-trusted",
        "permissions": ["must-not-be-trusted"],
    }
    claims.update(overrides)
    return claims


def _token(key: RSAKey, claims: dict[str, Any]) -> str:
    return jwt.encode(
        {"alg": "RS256", "kid": "test-key"},
        claims,
        key,
        algorithms=["RS256"],
    )


def _validator(
    public_key: RSAKey,
    *,
    counter: list[str] | None = None,
    discovery_mutator: Callable[[dict[str, Any]], None] | None = None,
) -> WorkforceOidcValidator:
    calls = counter if counter is not None else []
    public_jwks = {"keys": [public_key.as_dict(private=False)]}

    async def fetcher(url: str) -> dict[str, Any]:
        calls.append(url)
        if url.endswith("/.well-known/openid-configuration"):
            discovery: dict[str, Any] = {"issuer": ISSUER, "jwks_uri": JWKS_URI}
            if discovery_mutator is not None:
                discovery_mutator(discovery)
            return discovery
        if url == JWKS_URI:
            return public_jwks
        raise AssertionError(f"Unexpected URL: {url}")

    cache = OidcMetadataCache(
        issuer=ISSUER,
        environment="test",
        fetcher=fetcher,
    )
    return WorkforceOidcValidator(_settings(), metadata_cache=cache)


def test_valid_token_returns_only_normalized_trusted_identity() -> None:
    private_key = _rsa_key()
    validator = _validator(private_key)

    identity = asyncio.run(validator.validate(_token(private_key, _claims())))

    assert identity.model_dump() == {
        "issuer": ISSUER,
        "subject": "workforce-user-123",
        "email": "user@example.com",
        "email_verified": True,
        "display_name": "Test User",
    }
    assert "tenant_id" not in type(identity).model_fields
    assert "permissions" not in type(identity).model_fields


@pytest.mark.parametrize(
    ("claim_overrides", "remove_claim"),
    [
        ({"iss": "http://localhost:8080/realms/wrong"}, None),
        ({"aud": "wrong-audience"}, None),
        ({"exp": int(time.time()) - 60}, None),
        ({"sub": ""}, None),
        ({}, "sub"),
    ],
)
def test_invalid_required_claims_fail_closed(
    claim_overrides: dict[str, Any],
    remove_claim: str | None,
) -> None:
    private_key = _rsa_key()
    validator = _validator(private_key)
    claims = _claims(**claim_overrides)
    if remove_claim is not None:
        claims.pop(remove_claim)

    with pytest.raises(AuthenticationError) as exc_info:
        asyncio.run(validator.validate(_token(private_key, claims)))

    assert exc_info.value.error_code == "UNAUTHENTICATED"
    assert str(exc_info.value) == "Authentication failed."


def test_invalid_signature_fails_closed() -> None:
    trusted_key = _rsa_key()
    attacker_key = _rsa_key()
    validator = _validator(trusted_key)

    with pytest.raises(AuthenticationError):
        asyncio.run(validator.validate(_token(attacker_key, _claims())))


def test_malformed_token_fails_without_leaking_raw_token(caplog: pytest.LogCaptureFixture) -> None:
    trusted_key = _rsa_key()
    validator = _validator(trusted_key)
    raw_token = "not-a-valid-jwt-secret-value"

    with pytest.raises(AuthenticationError) as exc_info:
        asyncio.run(validator.validate(raw_token))

    assert raw_token not in str(exc_info.value)
    assert raw_token not in caplog.text


def test_discovery_and_jwks_are_cached_within_ttl() -> None:
    private_key = _rsa_key()
    calls: list[str] = []
    validator = _validator(private_key, counter=calls)
    raw_token = _token(private_key, _claims())

    asyncio.run(validator.validate(raw_token))
    asyncio.run(validator.validate(raw_token))

    assert calls == [f"{ISSUER}/.well-known/openid-configuration", JWKS_URI]


def test_discovery_issuer_mismatch_fails_before_jwks_use() -> None:
    private_key = _rsa_key()

    def mutate(discovery: dict[str, Any]) -> None:
        discovery["issuer"] = "http://localhost:8080/realms/attacker"

    validator = _validator(private_key, discovery_mutator=mutate)

    with pytest.raises(AuthenticationError):
        asyncio.run(validator.validate(_token(private_key, _claims())))


def test_unverified_email_is_preserved_as_profile_data_but_marked_unverified() -> None:
    private_key = _rsa_key()
    validator = _validator(private_key)

    identity = asyncio.run(
        validator.validate(_token(private_key, _claims(email_verified=False, name="")))
    )

    assert identity.email == "user@example.com"
    assert identity.email_verified is False
    assert identity.display_name is None
