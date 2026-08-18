from __future__ import annotations

import asyncio
import json
from uuid import UUID

import httpx
from pydantic import SecretStr

from app.core.config import PlatformSettings, load_settings
from app.modules.providers.gateway import HttpProviderConnectivityGateway

TENANT_ID = UUID("00000000-0000-0000-0000-000000000298")
PROVIDER_KEY = "sk-provider-secret-never-real"
INTERNAL_TOKEN = "internal-token-never-real"
RAW_UPSTREAM = "RAW-UPSTREAM-BODY-MUST-NOT-ESCAPE"


def _settings() -> PlatformSettings:
    return load_settings(
        {
            "SERVIQ_ENV": "test",
            "SERVIQ_PUBLIC_BASE_URL": "http://localhost:3000",
            "SERVIQ_API_BASE_URL": "http://localhost:8000",
            "DATABASE_URL": "postgresql://serviq:test@localhost:5432/serviq",
            "VALKEY_URL": "valkey://localhost:6379/0",
            "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
            "OBJECT_STORAGE_ENDPOINT": "http://localhost:8333",
            "OBJECT_STORAGE_BUCKET": "serviq-test",
            "OBJECT_STORAGE_ACCESS_KEY": "test-access",
            "OBJECT_STORAGE_SECRET_KEY": "test-secret",
            "OIDC_ISSUER_URL": "http://localhost:8080/realms/serviq",
            "OIDC_CLIENT_ID": "serviq-test",
            "OIDC_CLIENT_SECRET": "test-oidc",
            "OIDC_REDIRECT_URI": "http://localhost:3000/auth/callback",
            "SESSION_SECRET": "test-session",
            "LLM_GATEWAY_URL": "http://llm-gateway.internal:8100",
            "LLM_GATEWAY_INTERNAL_TOKEN": INTERNAL_TOKEN,
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
            "LOG_LEVEL": "INFO",
            "SERVIQ_LOCAL_WEBHOOK_ALLOWLIST": "",
        }
    )


def test_internal_gateway_request_is_fixed_and_normalized() -> None:
    async def scenario() -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(
                200,
                json={"ok": False, "errorCode": "PROVIDER_AUTH_FAILED"},
            )

        gateway = HttpProviderConnectivityGateway(
            _settings(),
            transport=httpx.MockTransport(handler),
        )
        outcome = await gateway.test(
            tenant_id=TENANT_ID,
            provider="openai",
            api_key=SecretStr(PROVIDER_KEY),
            correlation_id="gateway-client-test",
        )

        assert outcome.ok is False
        assert outcome.error_code == "PROVIDER_AUTH_FAILED"
        assert len(seen) == 1
        request = seen[0]
        assert str(request.url) == (
            "http://llm-gateway.internal:8100/internal/v1/provider-connectivity-test"
        )
        assert request.headers["authorization"] == f"Bearer {INTERNAL_TOKEN}"
        payload = json.loads(request.content)
        assert payload == {
            "tenantId": str(TENANT_ID),
            "provider": "openai",
            "apiKey": PROVIDER_KEY,
            "correlationId": "gateway-client-test",
        }
        assert "model" not in payload
        assert "prompt" not in payload
        assert "baseUrl" not in payload

    asyncio.run(scenario())


def test_internal_gateway_raw_http_failures_are_redacted() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            del request
            return httpx.Response(
                500,
                text=f"{RAW_UPSTREAM} credential={PROVIDER_KEY}",
            )

        gateway = HttpProviderConnectivityGateway(
            _settings(),
            transport=httpx.MockTransport(handler),
        )
        outcome = await gateway.test(
            tenant_id=TENANT_ID,
            provider="openai",
            api_key=SecretStr(PROVIDER_KEY),
            correlation_id="raw-failure-test",
        )

        assert outcome.ok is False
        assert outcome.error_code == "PROVIDER_UNAVAILABLE"
        rendered = repr(outcome)
        assert RAW_UPSTREAM not in rendered
        assert PROVIDER_KEY not in rendered

    asyncio.run(scenario())


def test_internal_gateway_timeout_is_normalized_without_retry() -> None:
    async def scenario() -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            raise httpx.ReadTimeout("unsafe timeout detail", request=request)

        gateway = HttpProviderConnectivityGateway(
            _settings(),
            transport=httpx.MockTransport(handler),
        )
        outcome = await gateway.test(
            tenant_id=TENANT_ID,
            provider="openai",
            api_key=SecretStr(PROVIDER_KEY),
            correlation_id="timeout-test",
        )

        assert outcome.ok is False
        assert outcome.error_code == "PROVIDER_TIMEOUT"
        assert calls == 1
        assert "unsafe timeout detail" not in repr(outcome)
        assert PROVIDER_KEY not in repr(outcome)

    asyncio.run(scenario())
