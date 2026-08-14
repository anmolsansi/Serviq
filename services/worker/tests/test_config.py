from __future__ import annotations

import pytest

from app.core.config import SettingsError, load_settings

BASE_ENV: dict[str, str] = {
    "SERVIQ_ENV": "local",
    "SERVIQ_PUBLIC_BASE_URL": "http://localhost:3000",
    "SERVIQ_API_BASE_URL": "http://localhost:8000",
    "DATABASE_URL": "postgresql://serviq:serviq@localhost:5432/serviq",
    "VALKEY_URL": "valkey://localhost:6379/0",
    "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
    "OBJECT_STORAGE_ENDPOINT": "http://localhost:8333",
    "OBJECT_STORAGE_BUCKET": "serviq-local",
    "OBJECT_STORAGE_ACCESS_KEY": "local-placeholder",
    "OBJECT_STORAGE_SECRET_KEY": "local-placeholder",
    "OIDC_ISSUER_URL": "http://localhost:8080/realms/serviq",
    "OIDC_CLIENT_ID": "serviq-local",
    "OIDC_CLIENT_SECRET": "local-placeholder",
    "OIDC_REDIRECT_URI": "http://localhost:3000/auth/callback",
    "SESSION_SECRET": "local-placeholder",
    "LLM_GATEWAY_URL": "http://localhost:8100",
    "LLM_GATEWAY_INTERNAL_TOKEN": "local-placeholder",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
    "LOG_LEVEL": "INFO",
    "SERVIQ_LOCAL_WEBHOOK_ALLOWLIST": "localhost, 127.0.0.1",
}


def test_valid_local_settings_load() -> None:
    settings = load_settings(BASE_ENV)

    assert settings.serviq_env == "local"
    assert settings.local_webhook_allowlist == ("localhost", "127.0.0.1")


def test_unknown_environment_fails_safely() -> None:
    env = BASE_ENV | {"SERVIQ_ENV": "preview"}

    with pytest.raises(SettingsError) as error:
        load_settings(env)

    assert str(error.value) == "Invalid Serviq configuration fields: SERVIQ_ENV"
    assert "preview" not in str(error.value)


def test_malformed_url_fails_safely() -> None:
    malformed = "not-a-valid-http-url"
    env = BASE_ENV | {"SERVIQ_API_BASE_URL": malformed}

    with pytest.raises(SettingsError) as error:
        load_settings(env)

    assert "SERVIQ_API_BASE_URL" in str(error.value)
    assert malformed not in str(error.value)


def test_production_requires_nonempty_secrets_without_echoing_values() -> None:
    sentinel = "never-print-this-secret"
    env = BASE_ENV | {
        "SERVIQ_ENV": "production",
        "OBJECT_STORAGE_ACCESS_KEY": sentinel,
        "OBJECT_STORAGE_SECRET_KEY": sentinel,
        "OIDC_CLIENT_SECRET": sentinel,
        "SESSION_SECRET": sentinel,
        "LLM_GATEWAY_INTERNAL_TOKEN": "",
    }

    with pytest.raises(SettingsError) as error:
        load_settings(env)

    assert "LLM_GATEWAY_INTERNAL_TOKEN" in str(error.value)
    assert sentinel not in str(error.value)
