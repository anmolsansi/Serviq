from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import httpx
import pytest
from google import genai
from google.genai import errors, types
from pydantic import SecretStr

from app.adapters import AdapterContext, GeminiAdapter
from app.adapters.gemini import _default_client_factory, _normalize_gemini_error
from app.schemas import (
    GatewayErrorCode,
    GatewayProvider,
    GatewayProviderError,
    GatewayRequest,
    GatewayResponse,
    GatewayStreamEvent,
)

SECRET = "gemini-test-key-never-real"


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
            "correlationId": "corr-gemini-test",
        }
    )


def _context() -> AdapterContext:
    return AdapterContext(
        provider=GatewayProvider.GEMINI,
        upstream_model="gemini-test-model",
        api_key=SecretStr(SECRET),
    )


def _response(
    *,
    text: str | None = "Provider answer",
    finish_reason: str | None = "STOP",
    response_id: str | None = "gemini-request-123",
    input_tokens: int | None = 17,
    output_tokens: int | None = 6,
) -> types.GenerateContentResponse:
    candidate = SimpleNamespace(finish_reason=finish_reason)
    usage = SimpleNamespace(
        prompt_token_count=input_tokens,
        candidates_token_count=output_tokens,
    )
    return cast(
        types.GenerateContentResponse,
        SimpleNamespace(
            text=text,
            candidates=[candidate] if finish_reason is not None else [],
            response_id=response_id,
            usage_metadata=usage,
        ),
    )


class _FakeModels:
    def __init__(
        self,
        *,
        response: types.GenerateContentResponse | None = None,
        stream_chunks: list[types.GenerateContentResponse] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.stream_chunks = stream_chunks or []
        self.error = error
        self.generate_calls: list[dict[str, object]] = []
        self.stream_calls: list[dict[str, object]] = []

    async def generate_content(
        self,
        *,
        model: str,
        contents: object,
        config: object,
    ) -> types.GenerateContentResponse:
        self.generate_calls.append(
            {"model": model, "contents": contents, "config": config}
        )
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise AssertionError("fake response was not configured")
        return self.response

    async def generate_content_stream(
        self,
        *,
        model: str,
        contents: object,
        config: object,
    ) -> AsyncIterator[types.GenerateContentResponse]:
        self.stream_calls.append(
            {"model": model, "contents": contents, "config": config}
        )
        if self.error is not None:
            raise self.error

        async def chunks() -> AsyncIterator[types.GenerateContentResponse]:
            for chunk in self.stream_chunks:
                yield chunk

        return chunks()


class _FakeAio:
    def __init__(self, models: _FakeModels) -> None:
        self.models = models
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class _FakeClient:
    def __init__(self, models: _FakeModels) -> None:
        self.aio = _FakeAio(models)
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _Factory:
    def __init__(self, client: _FakeClient) -> None:
        self.client = client
        self.calls: list[str] = []

    def __call__(self, api_key: str) -> genai.Client:
        self.calls.append(api_key)
        return cast(genai.Client, self.client)


async def _collect(stream: AsyncIterator[GatewayStreamEvent]) -> list[GatewayStreamEvent]:
    return [event async for event in stream]


def test_non_stream_success_normalizes_c4_response_and_metadata() -> None:
    async def scenario() -> None:
        models = _FakeModels(response=_response())
        fake_client = _FakeClient(models)
        factory = _Factory(fake_client)
        adapter = GeminiAdapter(factory)

        response = await adapter.generate(_request(), _context())

        assert isinstance(response, GatewayResponse)
        assert response.__class__.__module__ == "app.schemas.c4"
        assert response.content == "Provider answer"
        assert response.structured == {}
        assert response.provider is GatewayProvider.GEMINI
        assert response.upstream_model == "gemini-test-model"
        assert response.usage.input_tokens == 17
        assert response.usage.output_tokens == 6
        assert response.finish_reason == "STOP"
        assert response.request_id == "gemini-request-123"
        assert factory.calls == [SECRET]
        assert fake_client.aio.closed is True
        assert fake_client.closed is True

    asyncio.run(scenario())


def test_message_translation_preserves_meaning_and_applies_bounded_config() -> None:
    async def scenario() -> None:
        models = _FakeModels(response=_response())
        adapter = GeminiAdapter(_Factory(_FakeClient(models)))

        await adapter.generate(_request(), _context())

        call = models.generate_calls[0]
        assert call["model"] == "gemini-test-model"
        contents = cast(list[types.Content], call["contents"])
        assert [content.role for content in contents] == ["user", "model", "user"]
        assert [content.parts[0].text for content in contents if content.parts] == [
            "Summarize the case.",
            "I can help.",
            "Continue.",
        ]

        config = cast(types.GenerateContentConfig, call["config"])
        assert config.system_instruction == "Follow the support policy.\n\nBe concise."
        assert config.max_output_tokens == 321
        assert config.http_options is not None
        assert config.http_options.timeout == 12500
        assert config.http_options.retry_options is not None
        assert config.http_options.retry_options.attempts == 1
        assert config.response_mime_type is None
        assert config.response_json_schema is None

    asyncio.run(scenario())


def test_default_factory_forces_developer_api_even_when_enterprise_env_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    sentinel = cast(genai.Client, object())

    def fake_client(**kwargs: object) -> genai.Client:
        captured.update(kwargs)
        return sentinel

    monkeypatch.setenv("GOOGLE_GENAI_USE_ENTERPRISE", "true")
    monkeypatch.setattr("app.adapters.gemini.genai.Client", fake_client)

    assert _default_client_factory(SECRET) is sentinel
    assert captured == {"api_key": SECRET, "enterprise": False}


def test_structured_success_uses_native_json_schema_and_returns_serviq_data() -> None:
    async def scenario() -> None:
        models = _FakeModels(response=_response(text='{"answer":"resolved"}'))
        adapter = GeminiAdapter(_Factory(_FakeClient(models)))

        response = await adapter.generate(_request(structured=True), _context())

        assert response.content is None
        assert response.structured == {"answer": "resolved"}
        config = cast(types.GenerateContentConfig, models.generate_calls[0]["config"])
        assert config.response_mime_type == "application/json"
        assert config.response_json_schema is not None
        schema = cast(dict[str, object], config.response_json_schema)
        assert schema["type"] == "object"

    asyncio.run(scenario())


def test_text_stream_preserves_order_whitespace_and_terminal_metadata() -> None:
    async def scenario() -> None:
        chunks = [
            _response(
                text="Hello",
                finish_reason=None,
                response_id="stream-123",
                input_tokens=9,
                output_tokens=1,
            ),
            _response(
                text=" world",
                finish_reason=None,
                response_id="stream-123",
                input_tokens=9,
                output_tokens=2,
            ),
            _response(
                text="! ",
                finish_reason="STOP",
                response_id="stream-123",
                input_tokens=9,
                output_tokens=3,
            ),
        ]
        models = _FakeModels(stream_chunks=chunks)
        fake_client = _FakeClient(models)
        adapter = GeminiAdapter(_Factory(fake_client))

        events = await _collect(adapter.stream(_request(stream=True), _context()))

        assert "".join(event.content_delta or "" for event in events) == "Hello world! "
        terminal = events[-1]
        assert terminal.finish_reason == "STOP"
        assert terminal.request_id == "stream-123"
        assert terminal.usage is not None
        assert terminal.usage.input_tokens == 9
        assert terminal.usage.output_tokens == 3
        assert models.stream_calls[0]["model"] == "gemini-test-model"
        assert fake_client.aio.closed is True
        assert fake_client.closed is True

    asyncio.run(scenario())


def test_structured_stream_buffers_partial_json_then_emits_serviq_structure() -> None:
    async def scenario() -> None:
        chunks = [
            _response(
                text='{"answer":',
                finish_reason=None,
                response_id="stream-json-456",
            ),
            _response(
                text='"resolved"}',
                finish_reason="STOP",
                response_id="stream-json-456",
            ),
        ]
        models = _FakeModels(stream_chunks=chunks)
        adapter = GeminiAdapter(_Factory(_FakeClient(models)))

        events = await _collect(
            adapter.stream(_request(stream=True, structured=True), _context())
        )

        assert len(events) == 1
        assert events[0].content_delta is None
        assert events[0].structured_delta == {"answer": "resolved"}
        assert events[0].finish_reason == "STOP"
        assert events[0].request_id == "stream-json-456"

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("exception", "expected_code"),
    [
        (
            errors.ClientError(
                401,
                {
                    "error": {
                        "message": f"upstream auth body contains {SECRET}",
                        "status": "UNAUTHENTICATED",
                    }
                },
            ),
            GatewayErrorCode.PROVIDER_AUTH_FAILED,
        ),
        (
            errors.ClientError(
                429,
                {"error": {"message": "raw 429 body", "status": "RESOURCE_EXHAUSTED"}},
            ),
            GatewayErrorCode.PROVIDER_RATE_LIMITED,
        ),
        (
            httpx.ReadTimeout(
                f"upstream timeout contains {SECRET}",
                request=httpx.Request("POST", "https://generativelanguage.googleapis.com"),
            ),
            GatewayErrorCode.PROVIDER_TIMEOUT,
        ),
        (
            errors.ServerError(
                503,
                {"error": {"message": "raw outage body", "status": "UNAVAILABLE"}},
            ),
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
        ),
        (
            errors.ClientError(
                400,
                {"error": {"message": "raw invalid body", "status": "INVALID_ARGUMENT"}},
            ),
            GatewayErrorCode.PROVIDER_INVALID_REQUEST,
        ),
    ],
)
def test_provider_failures_map_to_safe_normalized_errors(
    exception: Exception,
    expected_code: GatewayErrorCode,
) -> None:
    error = _normalize_gemini_error(exception)

    assert error.code is expected_code
    assert SECRET not in str(error)
    assert "raw" not in str(error).lower()
    assert error.__class__.__module__ == "app.schemas.c4"


def test_sdk_error_from_generate_never_exposes_raw_body_or_key() -> None:
    async def scenario() -> None:
        upstream_error = errors.ClientError(
            401,
            {
                "error": {
                    "message": f"provider leaked key {SECRET}",
                    "status": "UNAUTHENTICATED",
                }
            },
        )
        models = _FakeModels(error=upstream_error)
        adapter = GeminiAdapter(_Factory(_FakeClient(models)))

        with pytest.raises(GatewayProviderError) as captured:
            await adapter.generate(_request(), _context())

        assert captured.value.code is GatewayErrorCode.PROVIDER_AUTH_FAILED
        assert SECRET not in str(captured.value)
        assert "provider leaked" not in str(captured.value).lower()

    asyncio.run(scenario())


def test_invalid_message_layout_fails_before_secret_client_is_constructed() -> None:
    async def scenario() -> None:
        models = _FakeModels(response=_response())
        factory = _Factory(_FakeClient(models))
        adapter = GeminiAdapter(factory)
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
        assert factory.calls == []
        assert models.generate_calls == []

    asyncio.run(scenario())


def test_system_only_request_is_explicitly_unsupported() -> None:
    async def scenario() -> None:
        factory = _Factory(_FakeClient(_FakeModels(response=_response())))
        adapter = GeminiAdapter(factory)

        with pytest.raises(GatewayProviderError) as captured:
            await adapter.generate(
                _request(messages=[{"role": "system", "content": "Policy only."}]),
                _context(),
            )

        assert captured.value.code is GatewayErrorCode.PROVIDER_INVALID_REQUEST
        assert factory.calls == []

    asyncio.run(scenario())


def test_malformed_structured_provider_output_fails_closed() -> None:
    async def scenario() -> None:
        models = _FakeModels(response=_response(text="not-json"))
        adapter = GeminiAdapter(_Factory(_FakeClient(models)))

        with pytest.raises(GatewayProviderError) as captured:
            await adapter.generate(_request(structured=True), _context())

        assert captured.value.code is GatewayErrorCode.PROVIDER_UNAVAILABLE
        assert "not-json" not in str(captured.value)

    asyncio.run(scenario())


def test_missing_key_provider_mismatch_and_wrong_stream_paths_fail_closed() -> None:
    async def scenario() -> None:
        models = _FakeModels(response=_response())
        factory = _Factory(_FakeClient(models))
        adapter = GeminiAdapter(factory)
        no_key = AdapterContext(
            provider=GatewayProvider.GEMINI,
            upstream_model="gemini-test-model",
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

        with pytest.raises(GatewayProviderError) as nonstream_error:
            await adapter.generate(_request(stream=True), _context())
        assert nonstream_error.value.code is GatewayErrorCode.PROVIDER_INVALID_REQUEST

        with pytest.raises(GatewayProviderError) as stream_error:
            await _collect(adapter.stream(_request(stream=False), _context()))
        assert stream_error.value.code is GatewayErrorCode.PROVIDER_INVALID_REQUEST

        assert models.generate_calls == []
        assert models.stream_calls == []

    asyncio.run(scenario())


def test_empty_stream_without_terminal_metadata_is_unavailable() -> None:
    async def scenario() -> None:
        models = _FakeModels(stream_chunks=[])
        adapter = GeminiAdapter(_Factory(_FakeClient(models)))

        with pytest.raises(GatewayProviderError) as captured:
            await _collect(adapter.stream(_request(stream=True), _context()))

        assert captured.value.code is GatewayErrorCode.PROVIDER_UNAVAILABLE

    asyncio.run(scenario())
