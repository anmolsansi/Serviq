from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import httpx
import pytest
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)
from openai import AsyncOpenAI
from pydantic import SecretStr

from app.adapters import AdapterContext, OpenAIAdapter
from app.adapters.openai import _normalize_openai_error
from app.schemas import (
    GatewayErrorCode,
    GatewayProvider,
    GatewayProviderError,
    GatewayRequest,
    GatewayStreamEvent,
)

SECRET = "sk-test-openai-never-real"


def _request(*, stream: bool = False, structured: bool = False) -> GatewayRequest:
    response_schema: dict[str, object] = {}
    if structured:
        response_schema = {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        }
    return GatewayRequest.model_validate(
        {
            "tenantId": str(UUID("11111111-1111-4111-8111-111111111111")),
            "modelAlias": "support-default",
            "purpose": "generation",
            "messages": [
                {"role": "system", "content": "Follow the support policy."},
                {"role": "user", "content": "Summarize the case."},
            ],
            "responseSchema": response_schema,
            "maxOutputTokens": 321,
            "timeoutMs": 12500,
            "stream": stream,
            "correlationId": "corr-openai-test",
        }
    )


def _context() -> AdapterContext:
    return AdapterContext(
        provider=GatewayProvider.OPENAI,
        upstream_model="gpt-test-model",
        api_key=SecretStr(SECRET),
    )


class _FakeCompletions:
    def __init__(
        self,
        result: object | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> Any:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


class _FakeClient:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.chat = SimpleNamespace(completions=completions)


class _Factory:
    def __init__(self, client: _FakeClient) -> None:
        self.client = client
        self.calls: list[tuple[str, float]] = []

    def __call__(self, api_key: str, timeout_seconds: float) -> AsyncOpenAI:
        self.calls.append((api_key, timeout_seconds))
        return cast(AsyncOpenAI, self.client)


def _completion(*, content: str | None = "Provider answer") -> object:
    return SimpleNamespace(
        id="chatcmpl-test-123",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=17, completion_tokens=6),
    )


class _ChunkStream:
    def __init__(self, chunks: list[object]) -> None:
        self._chunks = chunks

    def __aiter__(self) -> AsyncIterator[object]:
        async def iterator() -> AsyncIterator[object]:
            for chunk in self._chunks:
                yield chunk

        return iterator()


def _chunk(
    *,
    content: str | None = None,
    finish_reason: str | None = None,
    usage: object | None = None,
) -> object:
    choices: list[object] = []
    if content is not None or finish_reason is not None:
        choices.append(
            SimpleNamespace(
                delta=SimpleNamespace(content=content),
                finish_reason=finish_reason,
            )
        )
    return SimpleNamespace(
        id="chatcmpl-stream-456",
        choices=choices,
        usage=usage,
    )


async def _collect(stream: AsyncIterator[GatewayStreamEvent]) -> list[GatewayStreamEvent]:
    return [event async for event in stream]


def test_non_stream_success_normalizes_c4_and_forwards_bounded_request() -> None:
    async def scenario() -> None:
        completions = _FakeCompletions(_completion())
        factory = _Factory(_FakeClient(completions))
        adapter = OpenAIAdapter(factory)
        request = _request()

        response = await adapter.generate(request, _context())

        assert response.content == "Provider answer"
        assert response.structured == {}
        assert response.provider is GatewayProvider.OPENAI
        assert response.upstream_model == "gpt-test-model"
        assert response.usage.input_tokens == 17
        assert response.usage.output_tokens == 6
        assert response.finish_reason == "stop"
        assert response.request_id == "chatcmpl-test-123"
        assert response.__class__.__module__ == "app.schemas.c4"

        assert factory.calls == [(SECRET, 12.5)]
        call = completions.calls[0]
        assert call["model"] == "gpt-test-model"
        assert call["max_completion_tokens"] == 321
        assert call["timeout"] == 12.5
        assert "stream" not in call
        messages = cast(list[dict[str, str]], call["messages"])
        assert messages == [
            {"role": "system", "content": "Follow the support policy."},
            {"role": "user", "content": "Summarize the case."},
        ]

    asyncio.run(scenario())


def test_structured_success_uses_json_schema_and_returns_serviq_structure() -> None:
    async def scenario() -> None:
        completions = _FakeCompletions(_completion(content='{"answer":"resolved"}'))
        factory = _Factory(_FakeClient(completions))
        adapter = OpenAIAdapter(factory)

        response = await adapter.generate(_request(structured=True), _context())

        assert response.content is None
        assert response.structured == {"answer": "resolved"}
        response_format = cast(dict[str, object], completions.calls[0]["response_format"])
        assert response_format["type"] == "json_schema"
        json_schema = cast(dict[str, object], response_format["json_schema"])
        assert json_schema["strict"] is True
        assert json_schema["name"] == "serviq_response"

    asyncio.run(scenario())


def test_stream_preserves_order_whitespace_and_terminal_metadata() -> None:
    async def scenario() -> None:
        upstream = _ChunkStream(
            [
                _chunk(content="Hello"),
                _chunk(content=" world"),
                _chunk(content="! "),
                _chunk(finish_reason="stop"),
                _chunk(usage=SimpleNamespace(prompt_tokens=9, completion_tokens=3)),
            ]
        )
        completions = _FakeCompletions(upstream)
        adapter = OpenAIAdapter(_Factory(_FakeClient(completions)))

        events = await _collect(adapter.stream(_request(stream=True), _context()))

        assert "".join(event.content_delta or "" for event in events) == "Hello world! "
        terminal = events[-1]
        assert terminal.finish_reason == "stop"
        assert terminal.request_id == "chatcmpl-stream-456"
        assert terminal.usage is not None
        assert terminal.usage.input_tokens == 9
        assert terminal.usage.output_tokens == 3
        call = completions.calls[0]
        assert call["stream"] is True
        assert call["stream_options"] == {"include_usage": True}

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("exception", "expected_code"),
    [
        (
            AuthenticationError(
                f"upstream auth body contains {SECRET}",
                response=httpx.Response(
                    401,
                    request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
                ),
                body={"secret": SECRET},
            ),
            GatewayErrorCode.PROVIDER_AUTH_FAILED,
        ),
        (
            RateLimitError(
                "raw 429 body",
                response=httpx.Response(
                    429,
                    request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
                ),
                body={},
            ),
            GatewayErrorCode.PROVIDER_RATE_LIMITED,
        ),
        (
            APITimeoutError(
                request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
            ),
            GatewayErrorCode.PROVIDER_TIMEOUT,
        ),
        (
            APIConnectionError(
                request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
            ),
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
        ),
        (
            InternalServerError(
                "raw 500 body",
                response=httpx.Response(
                    500,
                    request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
                ),
                body={},
            ),
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
        ),
        (
            BadRequestError(
                "raw invalid body",
                response=httpx.Response(
                    400,
                    request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
                ),
                body={},
            ),
            GatewayErrorCode.PROVIDER_INVALID_REQUEST,
        ),
    ],
)
def test_sdk_failures_map_to_safe_normalized_errors(
    exception: Exception,
    expected_code: GatewayErrorCode,
) -> None:
    error = _normalize_openai_error(exception)

    assert error.code is expected_code
    assert SECRET not in str(error)
    assert "raw" not in str(error).lower()
    assert error.__class__.__module__ == "app.schemas.c4"


def test_missing_key_fails_closed_without_creating_sdk_client() -> None:
    async def scenario() -> None:
        completions = _FakeCompletions(_completion())
        factory = _Factory(_FakeClient(completions))
        adapter = OpenAIAdapter(factory)
        context = AdapterContext(
            provider=GatewayProvider.OPENAI,
            upstream_model="gpt-test-model",
            api_key=None,
        )

        with pytest.raises(GatewayProviderError) as captured:
            await adapter.generate(_request(), context)

        assert captured.value.code is GatewayErrorCode.PROVIDER_AUTH_FAILED
        assert factory.calls == []

    asyncio.run(scenario())


def test_provider_mismatch_and_wrong_stream_path_fail_before_network() -> None:
    async def scenario() -> None:
        factory = _Factory(_FakeClient(_FakeCompletions(_completion())))
        adapter = OpenAIAdapter(factory)
        wrong_provider = AdapterContext(
            provider=GatewayProvider.ANTHROPIC,
            upstream_model="claude-test",
            api_key=SecretStr(SECRET),
        )

        with pytest.raises(GatewayProviderError) as provider_error:
            await adapter.generate(_request(), wrong_provider)
        assert provider_error.value.code is GatewayErrorCode.PROVIDER_INVALID_REQUEST

        with pytest.raises(GatewayProviderError) as stream_error:
            await _collect(adapter.stream(_request(stream=False), _context()))
        assert stream_error.value.code is GatewayErrorCode.PROVIDER_INVALID_REQUEST
        assert factory.calls == []

    asyncio.run(scenario())
