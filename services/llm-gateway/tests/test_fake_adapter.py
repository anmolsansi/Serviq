from __future__ import annotations

import asyncio
import socket
from collections.abc import AsyncIterator
from uuid import UUID

import pytest

from app.adapters import (
    FAKE_SCENARIOS,
    FAKE_UPSTREAM_MODEL,
    AdapterContext,
    FakeLLMAdapter,
    FakeScenario,
    LLMAdapter,
)
from app.schemas import (
    GatewayErrorCode,
    GatewayProvider,
    GatewayProviderError,
    GatewayRequest,
    GatewayResponse,
    GatewayStreamEvent,
)


def _request(*, stream: bool = False, structured: bool = False) -> GatewayRequest:
    schema: dict[str, object] = {}
    if structured:
        schema = {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "confidence": {"type": "number"},
            },
            "required": ["answer", "confidence"],
            "additionalProperties": False,
        }
    return GatewayRequest.model_validate(
        {
            "tenantId": str(UUID("11111111-1111-4111-8111-111111111111")),
            "modelAlias": "support-default",
            "purpose": "generation",
            "messages": [{"role": "user", "content": "Summarize this case."}],
            "responseSchema": schema,
            "maxOutputTokens": 1500,
            "timeoutMs": 20000,
            "stream": stream,
            "correlationId": "fake-test-correlation",
        }
    )


def _context() -> AdapterContext:
    return AdapterContext(
        provider=GatewayProvider.OPENAI,
        upstream_model=FAKE_UPSTREAM_MODEL,
        api_key=None,
    )


async def _stream_list(stream: AsyncIterator[GatewayStreamEvent]) -> list[GatewayStreamEvent]:
    return [event async for event in stream]


def test_scenario_registry_is_explicit_and_complete() -> None:
    assert frozenset(FAKE_SCENARIOS) == frozenset(FakeScenario)
    assert FAKE_UPSTREAM_MODEL == "serviq-fake-v1"
    assert "magic prompt" not in {scenario.value for scenario in FakeScenario}


def test_text_success_is_byte_for_byte_deterministic() -> None:
    async def scenario() -> None:
        adapter: LLMAdapter = FakeLLMAdapter(FakeScenario.TEXT_SUCCESS)
        request = _request()
        context = _context()

        first = await adapter.generate(request, context)
        second = await adapter.generate(request, context)

        assert first.model_dump_json(by_alias=True) == second.model_dump_json(by_alias=True)
        assert first.content == "Serviq deterministic fake response."
        assert first.structured == {}
        assert first.provider is GatewayProvider.OPENAI
        assert first.upstream_model == FAKE_UPSTREAM_MODEL
        assert first.request_id is not None
        assert first.request_id.startswith("fake_")

    asyncio.run(scenario())


def test_structured_success_matches_the_fixture_schema_semantics() -> None:
    async def scenario() -> None:
        response = await FakeLLMAdapter(FakeScenario.STRUCTURED_SUCCESS).generate(
            _request(structured=True),
            _context(),
        )
        assert response.content is None
        assert response.structured == {
            "answer": "deterministic",
            "confidence": 1.0,
        }
        assert isinstance(response.structured["answer"], str)
        assert isinstance(response.structured["confidence"], float)

    asyncio.run(scenario())


def test_malformed_structured_scenario_is_predictably_invalid_for_same_schema() -> None:
    async def scenario() -> None:
        response = await FakeLLMAdapter(FakeScenario.MALFORMED_STRUCTURED).generate(
            _request(structured=True),
            _context(),
        )
        assert response.structured == {
            "answer": 123,
            "confidence": "not-a-number",
        }
        assert not isinstance(response.structured["answer"], str)
        assert not isinstance(response.structured["confidence"], float)

    asyncio.run(scenario())


def test_stream_success_is_ordered_deterministic_and_matches_nonstream_text() -> None:
    async def scenario() -> None:
        adapter = FakeLLMAdapter(FakeScenario.STREAM_SUCCESS)
        request = _request(stream=True)
        context = _context()

        first = await _stream_list(adapter.stream(request, context))
        second = await _stream_list(adapter.stream(request, context))
        first_json = [event.model_dump_json(by_alias=True) for event in first]
        second_json = [event.model_dump_json(by_alias=True) for event in second]
        assert first_json == second_json

        content = "".join(event.content_delta or "" for event in first)
        terminal = first[-1]
        nonstream: GatewayResponse = await adapter.generate(request, context)

        assert content == "Serviq deterministic fake response."
        assert nonstream.content == content
        assert terminal.finish_reason == "stop"
        assert terminal.usage is not None
        assert terminal.usage.input_tokens == 42
        assert terminal.usage.output_tokens == 7
        assert terminal.request_id == nonstream.request_id

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("fake_scenario", "expected_code"),
    [
        (FakeScenario.TIMEOUT, GatewayErrorCode.PROVIDER_TIMEOUT),
        (FakeScenario.RATE_LIMITED, GatewayErrorCode.PROVIDER_RATE_LIMITED),
        (FakeScenario.UNAVAILABLE, GatewayErrorCode.PROVIDER_UNAVAILABLE),
        (FakeScenario.AUTH_FAILED, GatewayErrorCode.PROVIDER_AUTH_FAILED),
    ],
)
def test_failure_scenarios_raise_only_normalized_gateway_errors(
    fake_scenario: FakeScenario,
    expected_code: GatewayErrorCode,
) -> None:
    async def scenario() -> None:
        adapter = FakeLLMAdapter(fake_scenario)
        with pytest.raises(GatewayProviderError) as captured:
            await adapter.generate(_request(), _context())
        assert captured.value.code is expected_code
        assert captured.value.__cause__ is None

    asyncio.run(scenario())


def test_non_stream_scenario_rejects_stream_call_with_normalized_invalid_request() -> None:
    async def scenario() -> None:
        adapter = FakeLLMAdapter(FakeScenario.TEXT_SUCCESS)
        with pytest.raises(GatewayProviderError) as captured:
            await _stream_list(adapter.stream(_request(stream=True), _context()))
        assert captured.value.code is GatewayErrorCode.PROVIDER_INVALID_REQUEST

    asyncio.run(scenario())


def test_adapter_never_opens_network_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    def deny_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("fake adapter attempted network access")

    monkeypatch.setattr(socket.socket, "connect", deny_network)

    async def scenario() -> None:
        context = _context()
        await FakeLLMAdapter(FakeScenario.TEXT_SUCCESS).generate(_request(), context)
        await FakeLLMAdapter(FakeScenario.STRUCTURED_SUCCESS).generate(
            _request(structured=True),
            context,
        )
        await _stream_list(
            FakeLLMAdapter(FakeScenario.STREAM_SUCCESS).stream(
                _request(stream=True),
                context,
            )
        )

    asyncio.run(scenario())
