from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import httpx
import pytest
from anthropic import (
    APIConnectionError,
    APITimeoutError,
    AsyncAnthropic,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)
from pydantic import SecretStr

from app.adapters import AdapterContext, AnthropicAdapter
from app.adapters.anthropic import _normalize_anthropic_error
from app.schemas import (
    GatewayErrorCode,
    GatewayProvider,
    GatewayProviderError,
    GatewayRequest,
    GatewayStreamEvent,
)

SECRET = "sk-ant-test-never-real"


def _request(
    *,
    stream: bool = False,
    structured: bool = False,
    messages: list[dict[str, str]] | None = None,
) -> GatewayRequest:
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
            "messages": messages
            or [
                {"role": "system", "content": "Follow the support policy."},
                {"role": "system", "content": "Be concise."},
                {"role": "user", "content": "Summarize the case."},
                {"role": "assistant", "content": "I can help."},
                {"role": "user", "content": "Continue."},
            ],
            "responseSchema": response_schema,
            "maxOutputTokens": 321,
            "timeoutMs": 12500,
            "stream": stream,
            "correlationId": "corr-anthropic-test",
        }
    )


def _context() -> AdapterContext:
    return AdapterContext(
        provider=GatewayProvider.ANTHROPIC,
        upstream_model="claude-test-model",
        api_key=SecretStr(SECRET),
    )


class _FakeMessages:
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
    def __init__(self, messages: _FakeMessages) -> None:
        self.messages = messages


class _Factory:
    def __init__(self, client: _FakeClient) -> None:
        self.client = client
        self.calls: list[tuple[str, float]] = []

    def __call__(self, api_key: str, timeout_seconds: float) -> AsyncAnthropic:
        self.calls.append((api_key, timeout_seconds))
        return cast(AsyncAnthropic, self.client)


def _message(*, text: str = "Provider answer", stop_reason: str = "end_turn") -> object:
    return SimpleNamespace(
        id="msg-test-123",
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=17, output_tokens=6),
    )


class _EventStream:
    def __init__(self, events: list[object]) -> None:
        self._events = events

    def __aiter__(self) -> AsyncIterator[object]:
        async def iterator() -> AsyncIterator[object]:
            for event in self._events:
                yield event

        return iterator()


def _message_start() -> object:
    return SimpleNamespace(
        type="message_start",
        message=SimpleNamespace(
            id="msg-stream-456",
            usage=SimpleNamespace(input_tokens=9, output_tokens=0),
        ),
    )


def _text_delta(text: str) -> object:
    return SimpleNamespace(
        type="content_block_delta",
        delta=SimpleNamespace(type="text_delta", text=text),
    )


def _message_delta(*, stop_reason: str = "end_turn", output_tokens: int = 3) -> object:
    return SimpleNamespace(
        type="message_delta",
        delta=SimpleNamespace(stop_reason=stop_reason),
        usage=SimpleNamespace(input_tokens=None, output_tokens=output_tokens),
    )


async def _collect(stream: AsyncIterator[GatewayStreamEvent]) -> list[GatewayStreamEvent]:
    return [event async for event in stream]


def test_non_stream_success_translates_system_and_preserves_conversation_order() -> None:
    async def scenario() -> None:
        messages_api = _FakeMessages(_message())
        factory = _Factory(_FakeClient(messages_api))
        adapter = AnthropicAdapter(factory)

        response = await adapter.generate(_request(), _context())

        assert response.content == "Provider answer"
        assert response.structured == {}
        assert response.provider is GatewayProvider.ANTHROPIC
        assert response.upstream_model == "claude-test-model"
        assert response.usage.input_tokens == 17
        assert response.usage.output_tokens == 6
        assert response.finish_reason == "end_turn"
        assert response.request_id == "msg-test-123"
        assert response.__class__.__module__ == "app.schemas.c4"

        assert factory.calls == [(SECRET, 12.5)]
        call = messages_api.calls[0]
        assert call["model"] == "claude-test-model"
        assert call["max_tokens"] == 321
        assert call["timeout"] == 12.5
        assert call["system"] == "Follow the support policy.\n\nBe concise."
        assert call["messages"] == [
            {"role": "user", "content": "Summarize the case."},
            {"role": "assistant", "content": "I can help."},
            {"role": "user", "content": "Continue."},
        ]

    asyncio.run(scenario())


def test_system_message_after_conversation_fails_explicitly() -> None:
    async def scenario() -> None:
        factory = _Factory(_FakeClient(_FakeMessages(_message())))
        adapter = AnthropicAdapter(factory)
        request = _request(
            messages=[
                {"role": "user", "content": "First."},
                {"role": "system", "content": "Late policy."},
            ]
        )

        with pytest.raises(GatewayProviderError) as captured:
            await adapter.generate(request, _context())

        assert captured.value.code is GatewayErrorCode.PROVIDER_INVALID_REQUEST
        assert "system" in str(captured.value).lower()
        assert factory.calls == [(SECRET, 12.5)]

    asyncio.run(scenario())


def test_structured_success_uses_output_config_and_returns_serviq_structure() -> None:
    async def scenario() -> None:
        messages_api = _FakeMessages(_message(text='{"answer":"resolved"}'))
        adapter = AnthropicAdapter(_Factory(_FakeClient(messages_api)))

        response = await adapter.generate(_request(structured=True), _context())

        assert response.content is None
        assert response.structured == {"answer": "resolved"}
        output_config = cast(dict[str, object], messages_api.calls[0]["output_config"])
        output_format = cast(dict[str, object], output_config["format"])
        assert output_format["type"] == "json_schema"
        schema = cast(dict[str, object], output_format["schema"])
        assert schema["type"] == "object"

    asyncio.run(scenario())


def test_text_stream_preserves_order_whitespace_and_terminal_metadata() -> None:
    async def scenario() -> None:
        upstream = _EventStream(
            [
                _message_start(),
                _text_delta("Hello"),
                _text_delta(" world"),
                _text_delta("! "),
                _message_delta(),
                SimpleNamespace(type="message_stop"),
            ]
        )
        messages_api = _FakeMessages(upstream)
        adapter = AnthropicAdapter(_Factory(_FakeClient(messages_api)))

        events = await _collect(adapter.stream(_request(stream=True), _context()))

        assert "".join(event.content_delta or "" for event in events) == "Hello world! "
        terminal = events[-1]
        assert terminal.finish_reason == "end_turn"
        assert terminal.request_id == "msg-stream-456"
        assert terminal.usage is not None
        assert terminal.usage.input_tokens == 9
        assert terminal.usage.output_tokens == 3
        assert messages_api.calls[0]["stream"] is True

    asyncio.run(scenario())


def test_structured_stream_emits_provider_neutral_structured_delta() -> None:
    async def scenario() -> None:
        upstream = _EventStream(
            [
                _message_start(),
                _text_delta('{"answer":'),
                _text_delta('"resolved"}'),
                _message_delta(output_tokens=5),
            ]
        )
        adapter = AnthropicAdapter(_Factory(_FakeClient(_FakeMessages(upstream))))

        events = await _collect(
            adapter.stream(_request(stream=True, structured=True), _context())
        )

        assert events[0].content_delta is None
        assert events[0].structured_delta == {"answer": "resolved"}
        assert events[-1].finish_reason == "end_turn"

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("exception", "expected_code"),
    [
        (
            AuthenticationError(
                f"upstream auth body contains {SECRET}",
                response=httpx.Response(
                    401,
                    request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
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
                    request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
                ),
                body={},
            ),
            GatewayErrorCode.PROVIDER_RATE_LIMITED,
        ),
        (
            APITimeoutError(
                httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            ),
            GatewayErrorCode.PROVIDER_TIMEOUT,
        ),
        (
            APIConnectionError(
                request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            ),
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
        ),
        (
            InternalServerError(
                "raw 500 body",
                response=httpx.Response(
                    500,
                    request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
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
                    request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
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
    error = _normalize_anthropic_error(exception)

    assert error.code is expected_code
    assert SECRET not in str(error)
    assert "raw" not in str(error).lower()
    assert error.__class__.__module__ == "app.schemas.c4"


def test_missing_key_provider_mismatch_and_wrong_stream_path_fail_closed() -> None:
    async def scenario() -> None:
        messages_api = _FakeMessages(_message())
        factory = _Factory(_FakeClient(messages_api))
        adapter = AnthropicAdapter(factory)
        no_key = AdapterContext(
            provider=GatewayProvider.ANTHROPIC,
            upstream_model="claude-test-model",
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
        assert messages_api.calls == []

    asyncio.run(scenario())
