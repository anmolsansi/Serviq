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
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)
from pydantic import SecretStr, ValidationError

import app.adapters.openrouter as openrouter_module
from app.adapters import AdapterContext, OpenRouterAdapter
from app.adapters.openrouter import (
    OPENROUTER_BASE_URL,
    _normalize_embedded_openrouter_error,
    _normalize_openrouter_error,
)
from app.schemas import (
    GatewayErrorCode,
    GatewayProvider,
    GatewayProviderError,
    GatewayRequest,
    GatewayStreamEvent,
)

SECRET = "sk-or-test-never-real"
UPSTREAM_MODEL = "anthropic/claude-test-model"


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
            "modelAlias": "support-openrouter",
            "purpose": "generation",
            "messages": [
                {"role": "system", "content": "Follow the support policy."},
                {"role": "user", "content": "Summarize the case."},
                {"role": "assistant", "content": "I can help."},
                {"role": "user", "content": "Continue."},
            ],
            "responseSchema": response_schema,
            "maxOutputTokens": 321,
            "timeoutMs": 12500,
            "stream": stream,
            "correlationId": "corr-openrouter-test",
        }
    )


def _context() -> AdapterContext:
    return AdapterContext(
        provider=GatewayProvider.OPENROUTER,
        upstream_model=UPSTREAM_MODEL,
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
        self.close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1


class _Factory:
    def __init__(self, client: _FakeClient) -> None:
        self.client = client
        self.calls: list[tuple[str, float]] = []

    def __call__(self, api_key: str, timeout_seconds: float) -> AsyncOpenAI:
        self.calls.append((api_key, timeout_seconds))
        return cast(AsyncOpenAI, self.client)


def _completion(
    *,
    content: str | None = "Provider answer",
    finish_reason: str = "stop",
    choice_extra: dict[str, object] | None = None,
) -> object:
    return SimpleNamespace(
        id="gen-openrouter-test-123",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason=finish_reason,
                model_extra=choice_extra or {},
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
    error: dict[str, object] | None = None,
) -> object:
    choices: list[object] = []
    if content is not None or finish_reason is not None:
        choices.append(
            SimpleNamespace(
                delta=SimpleNamespace(content=content),
                finish_reason=finish_reason,
                model_extra={},
            )
        )
    model_extra: dict[str, object] = {}
    if error is not None:
        model_extra["error"] = error
    return SimpleNamespace(
        id="gen-openrouter-stream-456",
        choices=choices,
        usage=usage,
        model_extra=model_extra,
    )


async def _collect(stream: AsyncIterator[GatewayStreamEvent]) -> list[GatewayStreamEvent]:
    return [event async for event in stream]


def test_default_client_factory_pins_openrouter_destination_and_disables_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    sentinel = cast(AsyncOpenAI, SimpleNamespace())

    def fake_client(**kwargs: object) -> AsyncOpenAI:
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(openrouter_module, "AsyncOpenAI", fake_client)

    client = openrouter_module._default_client_factory(SECRET, 12.5)

    assert client is sentinel
    assert captured == {
        "api_key": SECRET,
        "base_url": OPENROUTER_BASE_URL,
        "timeout": 12.5,
        "max_retries": 0,
    }


def test_non_stream_success_uses_validated_model_and_normalizes_c4() -> None:
    async def scenario() -> None:
        completions = _FakeCompletions(_completion())
        client = _FakeClient(completions)
        factory = _Factory(client)
        adapter = OpenRouterAdapter(factory)

        response = await adapter.generate(_request(), _context())

        assert response.content == "Provider answer"
        assert response.structured == {}
        assert response.provider is GatewayProvider.OPENROUTER
        assert response.upstream_model == UPSTREAM_MODEL
        assert response.usage.input_tokens == 17
        assert response.usage.output_tokens == 6
        assert response.finish_reason == "stop"
        assert response.request_id == "gen-openrouter-test-123"
        assert response.__class__.__module__ == "app.schemas.c4"

        assert factory.calls == [(SECRET, 12.5)]
        call = completions.calls[0]
        assert call["model"] == UPSTREAM_MODEL
        assert call["max_completion_tokens"] == 321
        assert call["timeout"] == 12.5
        assert "stream" not in call
        assert "base_url" not in call
        assert "extra_body" not in call
        messages = cast(list[dict[str, str]], call["messages"])
        assert messages == [
            {"role": "system", "content": "Follow the support policy."},
            {"role": "user", "content": "Summarize the case."},
            {"role": "assistant", "content": "I can help."},
            {"role": "user", "content": "Continue."},
        ]
        assert client.close_calls == 1

    asyncio.run(scenario())


def test_c4_rejects_arbitrary_base_url_and_endpoint_fields() -> None:
    payload = _request().model_dump(by_alias=True)
    payload["baseUrl"] = "https://attacker.example/api"
    payload["endpoint"] = "http://169.254.169.254/latest/meta-data"

    with pytest.raises(ValidationError):
        GatewayRequest.model_validate(payload)


def test_structured_success_uses_json_schema_and_returns_serviq_structure() -> None:
    async def scenario() -> None:
        completions = _FakeCompletions(_completion(content='{"answer":"resolved"}'))
        client = _FakeClient(completions)
        adapter = OpenRouterAdapter(_Factory(client))

        response = await adapter.generate(_request(structured=True), _context())

        assert response.content is None
        assert response.structured == {"answer": "resolved"}
        response_format = cast(dict[str, object], completions.calls[0]["response_format"])
        assert response_format["type"] == "json_schema"
        json_schema = cast(dict[str, object], response_format["json_schema"])
        assert json_schema["strict"] is True
        assert json_schema["name"] == "serviq_response"
        assert client.close_calls == 1

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
        client = _FakeClient(completions)
        adapter = OpenRouterAdapter(_Factory(client))

        events = await _collect(adapter.stream(_request(stream=True), _context()))

        assert "".join(event.content_delta or "" for event in events) == "Hello world! "
        terminal = events[-1]
        assert terminal.finish_reason == "stop"
        assert terminal.request_id == "gen-openrouter-stream-456"
        assert terminal.usage is not None
        assert terminal.usage.input_tokens == 9
        assert terminal.usage.output_tokens == 3
        call = completions.calls[0]
        assert call["model"] == UPSTREAM_MODEL
        assert call["stream"] is True
        assert call["stream_options"] == {"include_usage": True}
        assert client.close_calls == 1

    asyncio.run(scenario())


def test_structured_stream_buffers_json_and_emits_provider_neutral_structure() -> None:
    async def scenario() -> None:
        upstream = _ChunkStream(
            [
                _chunk(content='{"answer":'),
                _chunk(content='"resolved"}'),
                _chunk(finish_reason="stop"),
                _chunk(usage=SimpleNamespace(prompt_tokens=8, completion_tokens=4)),
            ]
        )
        completions = _FakeCompletions(upstream)
        adapter = OpenRouterAdapter(_Factory(_FakeClient(completions)))

        events = await _collect(adapter.stream(_request(stream=True, structured=True), _context()))

        assert len(events) == 1
        terminal = events[0]
        assert terminal.content_delta is None
        assert terminal.structured_delta == {"answer": "resolved"}
        assert terminal.finish_reason == "stop"
        assert terminal.usage is not None
        assert terminal.usage.output_tokens == 4

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("exception", "expected_code"),
    [
        (
            AuthenticationError(
                f"upstream auth body contains {SECRET}",
                response=httpx.Response(
                    401,
                    request=httpx.Request(
                        "POST", f"{OPENROUTER_BASE_URL}/chat/completions"
                    ),
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
                    request=httpx.Request(
                        "POST", f"{OPENROUTER_BASE_URL}/chat/completions"
                    ),
                ),
                body={},
            ),
            GatewayErrorCode.PROVIDER_RATE_LIMITED,
        ),
        (
            APITimeoutError(
                request=httpx.Request("POST", f"{OPENROUTER_BASE_URL}/chat/completions")
            ),
            GatewayErrorCode.PROVIDER_TIMEOUT,
        ),
        (
            APIConnectionError(
                request=httpx.Request("POST", f"{OPENROUTER_BASE_URL}/chat/completions")
            ),
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
        ),
        (
            InternalServerError(
                "raw 502 html/provider body",
                response=httpx.Response(
                    502,
                    request=httpx.Request(
                        "POST", f"{OPENROUTER_BASE_URL}/chat/completions"
                    ),
                ),
                body={},
            ),
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
        ),
        (
            BadRequestError(
                "raw invalid model body",
                response=httpx.Response(
                    400,
                    request=httpx.Request(
                        "POST", f"{OPENROUTER_BASE_URL}/chat/completions"
                    ),
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
    error = _normalize_openrouter_error(exception)

    assert error.code is expected_code
    assert SECRET not in str(error)
    assert "raw" not in str(error).lower()
    assert "html" not in str(error).lower()
    assert error.__class__.__module__ == "app.schemas.c4"


@pytest.mark.parametrize(
    ("embedded", "expected_code"),
    [
        (
            {
                "code": 401,
                "message": f"raw credential {SECRET}",
                "metadata": {"error_type": "authentication"},
            },
            GatewayErrorCode.PROVIDER_AUTH_FAILED,
        ),
        (
            {
                "code": 429,
                "message": "raw rate response",
                "metadata": {"error_type": "rate_limit_exceeded"},
            },
            GatewayErrorCode.PROVIDER_RATE_LIMITED,
        ),
        (
            {
                "code": 408,
                "message": "raw timeout response",
                "metadata": {"error_type": "timeout"},
            },
            GatewayErrorCode.PROVIDER_TIMEOUT,
        ),
        (
            {
                "code": 502,
                "message": "raw upstream body",
                "metadata": {"error_type": "provider_unavailable"},
            },
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
        ),
        (
            {
                "code": 400,
                "message": "raw bad request",
                "metadata": {"error_type": "invalid_request"},
            },
            GatewayErrorCode.PROVIDER_INVALID_REQUEST,
        ),
    ],
)
def test_embedded_openrouter_errors_use_typed_category_without_leaking_body(
    embedded: dict[str, object],
    expected_code: GatewayErrorCode,
) -> None:
    error = _normalize_embedded_openrouter_error(embedded)

    assert error.code is expected_code
    assert SECRET not in str(error)
    assert "raw" not in str(error).lower()


def test_mid_stream_in_band_error_is_normalized_and_stops_stream() -> None:
    async def scenario() -> None:
        upstream = _ChunkStream(
            [
                _chunk(content="partial"),
                _chunk(
                    finish_reason="error",
                    error={
                        "code": 429,
                        "message": f"upstream raw {SECRET}",
                        "metadata": {"error_type": "rate_limit_exceeded"},
                    },
                ),
            ]
        )
        client = _FakeClient(_FakeCompletions(upstream))
        adapter = OpenRouterAdapter(_Factory(client))

        with pytest.raises(GatewayProviderError) as captured:
            await _collect(adapter.stream(_request(stream=True), _context()))

        assert captured.value.code is GatewayErrorCode.PROVIDER_RATE_LIMITED
        assert SECRET not in str(captured.value)
        assert "raw" not in str(captured.value).lower()
        assert client.close_calls == 1

    asyncio.run(scenario())


def test_non_stream_embedded_provider_error_is_not_returned_as_partial_success() -> None:
    async def scenario() -> None:
        embedded = {
            "code": 502,
            "message": f"provider disconnected {SECRET}",
            "metadata": {"error_type": "provider_unavailable"},
        }
        client = _FakeClient(
            _FakeCompletions(
                _completion(
                    content="partial output",
                    finish_reason="error",
                    choice_extra={"error": embedded},
                )
            )
        )
        adapter = OpenRouterAdapter(_Factory(client))

        with pytest.raises(GatewayProviderError) as captured:
            await adapter.generate(_request(), _context())

        assert captured.value.code is GatewayErrorCode.PROVIDER_UNAVAILABLE
        assert "partial output" not in str(captured.value)
        assert SECRET not in str(captured.value)
        assert client.close_calls == 1

    asyncio.run(scenario())


def test_missing_key_provider_mismatch_and_wrong_stream_path_fail_closed() -> None:
    async def scenario() -> None:
        completions = _FakeCompletions(_completion())
        factory = _Factory(_FakeClient(completions))
        adapter = OpenRouterAdapter(factory)
        no_key = AdapterContext(
            provider=GatewayProvider.OPENROUTER,
            upstream_model=UPSTREAM_MODEL,
            api_key=None,
        )

        with pytest.raises(GatewayProviderError) as missing_key:
            await adapter.generate(_request(), no_key)
        assert missing_key.value.code is GatewayErrorCode.PROVIDER_AUTH_FAILED

        wrong_provider = AdapterContext(
            provider=GatewayProvider.OPENAI,
            upstream_model="gpt-test-model",
            api_key=SecretStr(SECRET),
        )
        with pytest.raises(GatewayProviderError) as provider_error:
            await adapter.generate(_request(), wrong_provider)
        assert provider_error.value.code is GatewayErrorCode.PROVIDER_INVALID_REQUEST

        with pytest.raises(GatewayProviderError) as stream_error:
            await _collect(adapter.stream(_request(stream=False), _context()))
        assert stream_error.value.code is GatewayErrorCode.PROVIDER_INVALID_REQUEST

        assert factory.calls == []
        assert completions.calls == []

    asyncio.run(scenario())


def test_malformed_structured_output_and_empty_stream_fail_safely() -> None:
    async def scenario() -> None:
        malformed_client = _FakeClient(_FakeCompletions(_completion(content="not-json")))
        malformed_adapter = OpenRouterAdapter(_Factory(malformed_client))

        with pytest.raises(GatewayProviderError) as malformed:
            await malformed_adapter.generate(_request(structured=True), _context())
        assert malformed.value.code is GatewayErrorCode.PROVIDER_UNAVAILABLE

        empty_client = _FakeClient(_FakeCompletions(_ChunkStream([])))
        empty_adapter = OpenRouterAdapter(_Factory(empty_client))
        with pytest.raises(GatewayProviderError) as empty:
            await _collect(empty_adapter.stream(_request(stream=True), _context()))
        assert empty.value.code is GatewayErrorCode.PROVIDER_UNAVAILABLE

    asyncio.run(scenario())
