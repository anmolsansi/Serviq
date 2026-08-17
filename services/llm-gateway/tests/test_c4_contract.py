from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas import (
    MAX_OUTPUT_TOKENS,
    MAX_TIMEOUT_MS,
    GatewayError,
    GatewayErrorCode,
    GatewayMessage,
    GatewayProvider,
    GatewayProviderError,
    GatewayPurpose,
    GatewayRequest,
    GatewayResponse,
    GatewayStreamEvent,
    GatewayUsage,
    MessageRole,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> dict[str, object]:
    value = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_valid_request_round_trips_exact_wire_shape() -> None:
    fixture = _fixture("c4_request.json")
    request = GatewayRequest.model_validate(fixture)

    assert request.purpose is GatewayPurpose.GENERATION
    assert request.messages[0].role is MessageRole.SYSTEM
    assert request.max_output_tokens == MAX_OUTPUT_TOKENS == 1_500
    assert request.timeout_ms == MAX_TIMEOUT_MS == 20_000
    assert request.model_dump(mode="json", by_alias=True) == fixture


def test_valid_response_round_trips_exact_wire_shape() -> None:
    fixture = _fixture("c4_response.json")
    response = GatewayResponse.model_validate(fixture)

    assert response.provider is GatewayProvider.OPENAI
    assert response.usage.input_tokens == 24
    assert response.model_dump(mode="json", by_alias=True) == fixture


def test_provider_generated_text_preserves_boundary_whitespace() -> None:
    response = GatewayResponse(
        content="  indented answer  ",
        structured={},
        provider=GatewayProvider.OPENAI,
        upstreamModel="gpt-test",
        usage=GatewayUsage(inputTokens=1, outputTokens=2),
        finishReason="stop",
        requestId="req-whitespace",
    )
    event = GatewayStreamEvent(contentDelta=" word ")

    assert response.content == "  indented answer  "
    assert event.content_delta == " word "


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("purpose", "chat"),
        ("maxOutputTokens", 0),
        ("maxOutputTokens", MAX_OUTPUT_TOKENS + 1),
        ("timeoutMs", 0),
        ("timeoutMs", MAX_TIMEOUT_MS + 1),
        ("tenantId", "not-a-uuid"),
        ("modelAlias", "   "),
        ("correlationId", "   "),
    ],
)
def test_invalid_request_fields_are_rejected(field: str, value: object) -> None:
    fixture = _fixture("c4_request.json")
    fixture[field] = value

    with pytest.raises(ValidationError):
        GatewayRequest.model_validate(fixture)


def test_invalid_message_role_is_rejected() -> None:
    fixture = _fixture("c4_request.json")
    messages = fixture["messages"]
    assert isinstance(messages, list)
    assert isinstance(messages[0], dict)
    messages[0]["role"] = "tool"

    with pytest.raises(ValidationError):
        GatewayRequest.model_validate(fixture)


def test_unknown_request_and_message_fields_are_rejected() -> None:
    request_fixture = _fixture("c4_request.json")
    request_fixture["provider"] = "openai"
    with pytest.raises(ValidationError):
        GatewayRequest.model_validate(request_fixture)

    message_fixture = _fixture("c4_request.json")
    messages = message_fixture["messages"]
    assert isinstance(messages, list)
    assert isinstance(messages[0], dict)
    messages[0]["providerMetadata"] = {"secret": "should-not-exist"}
    with pytest.raises(ValidationError):
        GatewayRequest.model_validate(message_fixture)


def test_response_rejects_unknown_provider_and_fields() -> None:
    fixture = _fixture("c4_response.json")
    fixture["provider"] = "fake"
    with pytest.raises(ValidationError):
        GatewayResponse.model_validate(fixture)

    fixture = _fixture("c4_response.json")
    fixture["rawProviderResponse"] = {"providerSpecific": True}
    with pytest.raises(ValidationError):
        GatewayResponse.model_validate(fixture)


def test_stream_event_requires_normalized_payload_or_terminal_metadata() -> None:
    with pytest.raises(ValidationError):
        GatewayStreamEvent()

    event = GatewayStreamEvent(contentDelta="hello")
    assert event.model_dump(mode="json", by_alias=True, exclude_none=True) == {
        "contentDelta": "hello"
    }

    terminal = GatewayStreamEvent(
        finishReason="stop",
        usage=GatewayUsage(inputTokens=10, outputTokens=4),
        requestId="req-stream-1",
    )
    assert terminal.finish_reason == "stop"
    assert terminal.usage is not None
    assert terminal.usage.output_tokens == 4


def test_every_normalized_provider_error_is_provider_neutral() -> None:
    expected = {
        "PROVIDER_RATE_LIMITED",
        "PROVIDER_TIMEOUT",
        "PROVIDER_UNAVAILABLE",
        "PROVIDER_INVALID_REQUEST",
        "PROVIDER_AUTH_FAILED",
    }
    assert {code.value for code in GatewayErrorCode} == expected

    for code in GatewayErrorCode:
        error = GatewayError(code=code, message="normalized gateway failure")
        exception = GatewayProviderError(code, error.message)
        assert exception.code is code
        assert exception.error == error
        assert exception.__class__.__module__ == "app.schemas.c4"


def test_public_contract_types_are_owned_only_by_serviq_schema_module() -> None:
    public_types = (
        GatewayRequest,
        GatewayResponse,
        GatewayMessage,
        GatewayUsage,
        GatewayStreamEvent,
        GatewayError,
        GatewayProviderError,
    )
    assert all(item.__module__ == "app.schemas.c4" for item in public_types)
