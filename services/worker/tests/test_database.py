from __future__ import annotations

import pytest

from app.core.config import load_settings
from app.core.database import DatabaseConfigurationError, sqlalchemy_database_url

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


def test_plain_postgresql_url_uses_psycopg_dialect() -> None:
    settings = load_settings(BASE_ENV)

    assert sqlalchemy_database_url(settings).startswith("postgresql+psycopg://")


def test_already_adapted_database_url_is_preserved() -> None:
    settings = load_settings(
        BASE_ENV
        | {"DATABASE_URL": "postgresql+psycopg://serviq:serviq@localhost:5432/serviq"}
    )

    assert (
        sqlalchemy_database_url(settings)
        == "postgresql+psycopg://serviq:serviq@localhost:5432/serviq"
    )


def test_non_postgresql_database_url_fails_without_echoing_value() -> None:
    unsafe = "mysql://user:super-secret@localhost/database"
    settings = load_settings(BASE_ENV | {"DATABASE_URL": unsafe})

    with pytest.raises(DatabaseConfigurationError) as error:
        sqlalchemy_database_url(settings)

    assert str(error.value) == "DATABASE_URL must use the PostgreSQL scheme"
    assert unsafe not in str(error.value)
