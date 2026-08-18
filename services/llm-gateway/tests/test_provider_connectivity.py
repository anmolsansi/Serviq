from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import httpx
from pydantic import SecretStr

import app.connectivity as connectivity
from app.adapters import AdapterContext
from app.main import app
from app.schemas import (
    GatewayErrorCode,
    GatewayProvider,
    GatewayProviderError,
    GatewayRequest,
    GatewayResponse,
    GatewayStreamEvent,
    GatewayUsage,
)

SECRET = "sk-test-connectivity-never-real"


class RecordingAdapter:
    def __init__(self, *, error: GatewayErrorCode | None = None) -> None:
        self.error = error
        self.calls: list[tuple[GatewayRequest, AdapterContext]] = []

    async def generate(
        self,
        request: GatewayRequest,
        context: AdapterContext,
    ) -> GatewayResponse:
        self.calls.append((request, context))
        if self.error is not None:
            raise GatewayProviderError(self.error, "safe normalized failure")
        return GatewayResponse(
            content="THIS GENERATED CONTENT MUST NOT CROSS THE HEALTH ENDPOINT",
            structured={},
            provider=context.provider,
            upstreamModel=context.upstream_model,
            usage=GatewayUsage(inputTokens=1, outputTokens=1),
            finishReason="stop",
            requestId="provider-request-id-that-must-not-be-returned",
        )

    def stream(
        self,
        request: GatewayRequest,
        context: AdapterContext,
    ) -> AsyncIterator[GatewayStreamEvent]:
        del request, context

        async def events() -> AsyncIterator[GatewayStreamEvent]:
            if False:
                yield GatewayStreamEvent(contentDelta="unused")

        return events()


def _request(provider: GatewayProvider) -> connectivity.ProviderConnectivityRequest:
    return connectivity.ProviderConnectivityRequest(
        tenantId=uuid4(),
        provider=provider,
        apiKey=SecretStr(SECRET),
        correlationId="ope-298-test",
    )


def test_server_owned_models_and_fixed_request_shape() -> None:
    async def scenario() -> None:
        expected = {
            GatewayProvider.OPENAI: "gpt-5-nano",
            GatewayProvider.ANTHROPIC: "claude-haiku-4-5-20251001",
            GatewayProvider.GEMINI: "gemini-3.5-flash-lite",
            GatewayProvider.OPENROUTER: "openrouter/free",
        }
        for provider, model in expected.items():
            adapter = RecordingAdapter()
            response = await connectivity.run_connectivity_test(
                _request(provider),
                adapter=adapter,
            )
            assert response.ok is True
            assert response.error_code is None
            assert len(adapter.calls) == 1
            request, context = adapter.calls[0]
            assert context.provider is provider
            assert context.upstream_model == model
            assert context.api_key is not None
            assert context.api_key.get_secret_value() == SECRET
            assert request.model_alias == "__serviq_provider_connectivity_test__"
            assert request.max_output_tokens == 4
            assert request.timeout_ms == 5_000
            assert request.stream is False
            assert request.response_schema == {}
            assert len(request.messages) == 1
            assert request.messages[0].content == "Reply with OK."

    asyncio.run(scenario())


def test_normalized_provider_failure_is_returned_without_provider_detail() -> None:
    async def scenario() -> None:
        adapter = RecordingAdapter(error=GatewayErrorCode.PROVIDER_AUTH_FAILED)
        response = await connectivity.run_connectivity_test(
            _request(GatewayProvider.OPENAI),
            adapter=adapter,
        )
        assert response.ok is False
        assert response.error_code is GatewayErrorCode.PROVIDER_AUTH_FAILED
        assert "safe normalized failure" not in response.model_dump_json()
        assert SECRET not in response.model_dump_json()

    asyncio.run(scenario())


def test_private_route_requires_internal_auth_rejects_extra_controls_and_hides_content(
    monkeypatch: object,
) -> None:
    # pytest's MonkeyPatch is intentionally avoided in the annotation so this test file
    # remains compatible with the repository's strict dependency surface.
    from pytest import MonkeyPatch

    assert isinstance(monkeypatch, MonkeyPatch)
    typed_monkeypatch = monkeypatch

    async def scenario() -> None:
        typed_monkeypatch.setenv("LLM_GATEWAY_INTERNAL_TOKEN", "internal-test-token")
        adapter = RecordingAdapter()
        typed_monkeypatch.setattr(connectivity, "_adapter_for", lambda provider: adapter)
        transport = httpx.ASGITransport(app=app)
        payload = {
            "tenantId": str(UUID("00000000-0000-0000-0000-000000000001")),
            "provider": "openai",
            "apiKey": SECRET,
            "correlationId": "route-test",
        }
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            unauthorized = await client.post(
                "/internal/v1/provider-connectivity-test",
                json=payload,
            )
            assert unauthorized.status_code == 401
            assert adapter.calls == []

            caller_controlled = await client.post(
                "/internal/v1/provider-connectivity-test",
                headers={"Authorization": "Bearer internal-test-token"},
                json={
                    **payload,
                    "model": "attacker/model",
                    "prompt": "attacker prompt",
                    "baseUrl": "https://attacker.invalid",
                },
            )
            assert caller_controlled.status_code == 422
            assert adapter.calls == []

            successful = await client.post(
                "/internal/v1/provider-connectivity-test",
                headers={"Authorization": "Bearer internal-test-token"},
                json=payload,
            )
            assert successful.status_code == 200
            assert successful.json() == {"ok": True, "errorCode": None}
            assert SECRET not in successful.text
            assert "GENERATED CONTENT" not in successful.text
            assert "provider-request-id" not in successful.text
            assert len(adapter.calls) == 1

    asyncio.run(scenario())
