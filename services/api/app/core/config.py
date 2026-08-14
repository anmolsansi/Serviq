"""Typed platform configuration boundary for the Serviq API.

Only architecture-owned platform environment variables belong here. Tenant BYOK
provider credentials are intentionally excluded from process environment config.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Literal

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, HttpUrl, SecretStr, ValidationError

ServiqEnvironment = Literal["local", "test", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

PLATFORM_ENV_NAMES: tuple[str, ...] = (
    "SERVIQ_ENV",
    "SERVIQ_PUBLIC_BASE_URL",
    "SERVIQ_API_BASE_URL",
    "DATABASE_URL",
    "VALKEY_URL",
    "KAFKA_BOOTSTRAP_SERVERS",
    "OBJECT_STORAGE_ENDPOINT",
    "OBJECT_STORAGE_BUCKET",
    "OBJECT_STORAGE_ACCESS_KEY",
    "OBJECT_STORAGE_SECRET_KEY",
    "OIDC_ISSUER_URL",
    "OIDC_CLIENT_ID",
    "OIDC_CLIENT_SECRET",
    "OIDC_REDIRECT_URI",
    "SESSION_SECRET",
    "LLM_GATEWAY_URL",
    "LLM_GATEWAY_INTERNAL_TOKEN",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "LOG_LEVEL",
    "SERVIQ_LOCAL_WEBHOOK_ALLOWLIST",
)

PRODUCTION_SECRET_NAMES: tuple[str, ...] = (
    "OBJECT_STORAGE_ACCESS_KEY",
    "OBJECT_STORAGE_SECRET_KEY",
    "OIDC_CLIENT_SECRET",
    "SESSION_SECRET",
    "LLM_GATEWAY_INTERNAL_TOKEN",
)


class SettingsError(RuntimeError):
    """Safe configuration error that never includes raw environment values."""


class PlatformSettings(BaseModel):
    """Validated process-level Serviq platform configuration."""

    model_config = ConfigDict(extra="ignore", populate_by_name=False)

    serviq_env: ServiqEnvironment = Field(alias="SERVIQ_ENV")
    serviq_public_base_url: HttpUrl = Field(alias="SERVIQ_PUBLIC_BASE_URL")
    serviq_api_base_url: HttpUrl = Field(alias="SERVIQ_API_BASE_URL")
    database_url: AnyUrl = Field(alias="DATABASE_URL")
    valkey_url: AnyUrl = Field(alias="VALKEY_URL")
    kafka_bootstrap_servers: str = Field(alias="KAFKA_BOOTSTRAP_SERVERS", min_length=1)
    object_storage_endpoint: HttpUrl = Field(alias="OBJECT_STORAGE_ENDPOINT")
    object_storage_bucket: str = Field(alias="OBJECT_STORAGE_BUCKET", min_length=1)
    object_storage_access_key: SecretStr = Field(alias="OBJECT_STORAGE_ACCESS_KEY")
    object_storage_secret_key: SecretStr = Field(alias="OBJECT_STORAGE_SECRET_KEY")
    oidc_issuer_url: HttpUrl = Field(alias="OIDC_ISSUER_URL")
    oidc_client_id: str = Field(alias="OIDC_CLIENT_ID", min_length=1)
    oidc_client_secret: SecretStr = Field(alias="OIDC_CLIENT_SECRET")
    oidc_redirect_uri: HttpUrl = Field(alias="OIDC_REDIRECT_URI")
    session_secret: SecretStr = Field(alias="SESSION_SECRET")
    llm_gateway_url: HttpUrl = Field(alias="LLM_GATEWAY_URL")
    llm_gateway_internal_token: SecretStr = Field(alias="LLM_GATEWAY_INTERNAL_TOKEN")
    otel_exporter_otlp_endpoint: AnyUrl = Field(alias="OTEL_EXPORTER_OTLP_ENDPOINT")
    log_level: LogLevel = Field(alias="LOG_LEVEL")
    serviq_local_webhook_allowlist: str = Field(
        default="",
        alias="SERVIQ_LOCAL_WEBHOOK_ALLOWLIST",
    )

    @property
    def local_webhook_allowlist(self) -> tuple[str, ...]:
        """Return trimmed local-development webhook host entries."""

        return tuple(
            entry.strip()
            for entry in self.serviq_local_webhook_allowlist.split(",")
            if entry.strip()
        )


def _safe_error_fields(error: ValidationError) -> tuple[str, ...]:
    fields: set[str] = set()
    for detail in error.errors(include_input=False, include_url=False):
        location = detail.get("loc", ())
        if location:
            fields.add(str(location[0]))
        else:
            fields.add("configuration")
    return tuple(sorted(fields))


def load_settings(environ: Mapping[str, str] | None = None) -> PlatformSettings:
    """Load and validate the frozen Serviq platform environment contract.

    Validation errors name fields only. Raw values, including secret values, are
    never copied into the raised exception message.
    """

    source: Mapping[str, str] = os.environ if environ is None else environ

    if source.get("SERVIQ_ENV") == "production":
        missing_secrets = sorted(
            name for name in PRODUCTION_SECRET_NAMES if not source.get(name, "").strip()
        )
        if missing_secrets:
            names = ", ".join(missing_secrets)
            raise SettingsError(f"Missing required production configuration fields: {names}")

    payload = {name: source[name] for name in PLATFORM_ENV_NAMES if name in source}
    try:
        return PlatformSettings.model_validate(payload)
    except ValidationError as error:
        fields = ", ".join(_safe_error_fields(error))
        raise SettingsError(f"Invalid Serviq configuration fields: {fields}") from None
