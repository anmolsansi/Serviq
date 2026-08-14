from __future__ import annotations

import pytest

from app.core.config import load_settings
from app.core.database import DatabaseConfigurationError, sqlalchemy_database_url

BASE_ENV: dict[str, str] = {
    "SERVIQ_ENV": "test",
    "SERVIQ_PUBLIC_BASE_URL": "http://localhost:3000",
    "SERVIQ_API_BASE_URL": "http://localhost:8000",
    "DATABASE_URL": "postgresql://serviq:secret@localhost:5432/serviq",
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
    "SERVIQ_LOCAL_WEBHOOK_ALLOWLIST": "",
}


def test_plain_postgresql_url_is_adapted_to_psycopg() -> None:
    settings = load_settings(BASE_ENV)

    assert sqlalchemy_database_url(settings).startswith("postgresql+psycopg://")


def test_non_postgresql_database_scheme_fails_without_leaking_url() -> None:
    sentinel = "never-print-database-password"
    env = BASE_ENV | {"DATABASE_URL": f"mysql://serviq:{sentinel}@localhost:3306/serviq"}
    settings = load_settings(env)

    with pytest.raises(DatabaseConfigurationError) as error:
        sqlalchemy_database_url(settings)

    assert str(error.value) == "DATABASE_URL must use the PostgreSQL scheme"
    assert sentinel not in str(error.value)
