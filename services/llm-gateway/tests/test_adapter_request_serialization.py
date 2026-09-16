from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from pydantic import SecretStr

from app.adapters import AdapterContext, AnthropicAdapter, OpenAIAdapter, OpenRouterAdapter
from app.schemas import GatewayErrorCode, GatewayProvider, GatewayProviderError, GatewayRequest


@pytest.mark.parametrize(
    ("provider", "system"),
    [
        (GatewayProvider.OPENAI, True),
        (GatewayProvider.OPENROUTER, True),
        (GatewayProvider.ANTHROPIC, True),
        (GatewayProvider.ANTHROPIC, False),
    ],
)
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("structured", [False, True])
def test_optional_fields_are_omitted_from_sdk_http_requests(
    provider: GatewayProvider, system: bool, stream: bool, structured: bool
) -> None:
    async def scenario() -> None:
        bodies: list[dict[str, object]] = []

        def respond(request: httpx.Request) -> httpx.Response:
            bodies.append(json.loads(request.content))
            return httpx.Response(400, json={"error": {"message": "rejected"}})

        messages = [{"role": "user", "content": "Hello"}]
        if system:
            messages.insert(0, {"role": "system", "content": "Be concise."})
        schema = {"type": "object", "properties": {}} if structured else {}
        request = GatewayRequest.model_validate(
            {
                "tenantId": "11111111-1111-4111-8111-111111111111",
                "modelAlias": "support-default",
                "purpose": "generation",
                "messages": messages,
                "responseSchema": schema,
                "maxOutputTokens": 321,
                "timeoutMs": 12500,
                "stream": stream,
                "correlationId": "serialization-test",
            }
        )
        context = AdapterContext(
            provider=provider, upstream_model="test-model", api_key=SecretStr("test-key")
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            adapter: AnthropicAdapter | OpenAIAdapter | OpenRouterAdapter
            if provider is GatewayProvider.ANTHROPIC:
                anthropic_client = AsyncAnthropic(
                    api_key="test-key", http_client=http, max_retries=0
                )
                adapter = AnthropicAdapter(lambda key, timeout: anthropic_client)
            else:
                openai_client = AsyncOpenAI(api_key="test-key", http_client=http, max_retries=0)
                adapter_type = (
                    OpenAIAdapter if provider is GatewayProvider.OPENAI else OpenRouterAdapter
                )
                adapter = adapter_type(lambda key, timeout: openai_client)
            with pytest.raises(GatewayProviderError) as error:
                if stream:
                    async for _ in adapter.stream(request, context):
                        pass
                else:
                    await adapter.generate(request, context)
            assert error.value.code is GatewayErrorCode.PROVIDER_INVALID_REQUEST

        assert len(bodies) == 1
        body = bodies[0]
        assert body["model"] == "test-model"
        assert body.get("stream", False) is stream
        if provider is GatewayProvider.ANTHROPIC:
            assert body["max_tokens"] == 321
            assert body["messages"] == [messages[-1]]
            assert ("system" in body) is system
            if system:
                assert body["system"] == "Be concise."
            assert body.get("output_config") == (
                {"format": {"type": "json_schema", "schema": schema}} if structured else None
            )
            assert ("output_config" in body) is structured
        else:
            assert body["max_completion_tokens"] == 321
            assert body["messages"] == messages
            assert body.get("response_format") == (
                {
                    "type": "json_schema",
                    "json_schema": {"name": "serviq_response", "strict": True, "schema": schema},
                }
                if structured
                else None
            )
            assert ("response_format" in body) is structured
            if stream:
                assert body["stream_options"] == {"include_usage": True}

    asyncio.run(scenario())
