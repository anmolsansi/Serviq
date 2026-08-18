"""Narrow API-to-LLM-Gateway client for provider connectivity testing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from app.core.config import PlatformSettings, load_settings
from app.modules.providers.schemas import ProviderConnectivityErrorCode

_PRIVATE_TEST_PATH = "/internal/v1/provider-connectivity-test"
_GATEWAY_HTTP_TIMEOUT_SECONDS = 6.0


@dataclass(frozen=True)
class ProviderConnectivityOutcome:
    ok: bool
    error_code: ProviderConnectivityErrorCode | None = None


class ProviderConnectivityGateway(Protocol):
    async def test(
        self,
        *,
        tenant_id: UUID,
        provider: str,
        api_key: SecretStr,
        correlation_id: str,
    ) -> ProviderConnectivityOutcome: ...


class _GatewayResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    ok: bool
    error_code: ProviderConnectivityErrorCode | None = Field(default=None, alias="errorCode")


class HttpProviderConnectivityGateway:
    """Call only Serviq's fixed private gateway health-check route."""

    def __init__(
        self,
        settings: PlatformSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = f"{str(settings.llm_gateway_url).rstrip('/')}{_PRIVATE_TEST_PATH}"
        self._internal_token = settings.llm_gateway_internal_token
        self._transport = transport

    async def test(
        self,
        *,
        tenant_id: UUID,
        provider: str,
        api_key: SecretStr,
        correlation_id: str,
    ) -> ProviderConnectivityOutcome:
        headers = {
            "Authorization": f"Bearer {self._internal_token.get_secret_value()}",
            "Content-Type": "application/json",
        }
        payload = {
            "tenantId": str(tenant_id),
            "provider": provider,
            "apiKey": api_key.get_secret_value(),
            "correlationId": correlation_id,
        }

        try:
            async with httpx.AsyncClient(
                timeout=_GATEWAY_HTTP_TIMEOUT_SECONDS,
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                response = await client.post(self._url, headers=headers, json=payload)
        except httpx.TimeoutException:
            return ProviderConnectivityOutcome(ok=False, error_code="PROVIDER_TIMEOUT")
        except httpx.HTTPError:
            return ProviderConnectivityOutcome(ok=False, error_code="PROVIDER_UNAVAILABLE")

        if response.status_code != 200:
            return ProviderConnectivityOutcome(ok=False, error_code="PROVIDER_UNAVAILABLE")

        try:
            parsed = _GatewayResponse.model_validate(response.json())
        except (ValueError, ValidationError):
            return ProviderConnectivityOutcome(ok=False, error_code="PROVIDER_UNAVAILABLE")

        if parsed.ok and parsed.error_code is None:
            return ProviderConnectivityOutcome(ok=True)
        if not parsed.ok and parsed.error_code is not None:
            return ProviderConnectivityOutcome(ok=False, error_code=parsed.error_code)
        return ProviderConnectivityOutcome(ok=False, error_code="PROVIDER_UNAVAILABLE")


def build_provider_connectivity_gateway(
    settings: PlatformSettings | None = None,
) -> HttpProviderConnectivityGateway:
    return HttpProviderConnectivityGateway(load_settings() if settings is None else settings)
