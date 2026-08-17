"""Deterministic offline LLM adapter for CI, demos, and contract tests."""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from pydantic import JsonValue

from app.adapters.base import AdapterContext
from app.schemas import (
    GatewayErrorCode,
    GatewayProviderError,
    GatewayRequest,
    GatewayResponse,
    GatewayStreamEvent,
    GatewayUsage,
)

FAKE_UPSTREAM_MODEL = "serviq-fake-v1"
_TEXT = "Serviq deterministic fake response."
_STRUCTURED: dict[str, JsonValue] = {"answer": "deterministic", "confidence": 1.0}
_MALFORMED_STRUCTURED: dict[str, JsonValue] = {
    "answer": 123,
    "confidence": "not-a-number",
}


class FakeScenario(StrEnum):
    TEXT_SUCCESS = "text_success"
    STRUCTURED_SUCCESS = "structured_success"
    STREAM_SUCCESS = "stream_success"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    AUTH_FAILED = "auth_failed"
    MALFORMED_STRUCTURED = "malformed_structured"


@dataclass(frozen=True)
class FakeScenarioDefinition:
    content: str | None = None
    structured: dict[str, JsonValue] | None = None
    stream_chunks: tuple[str, ...] = ()
    error_code: GatewayErrorCode | None = None
    error_message: str | None = None


FAKE_SCENARIOS: Mapping[FakeScenario, FakeScenarioDefinition] = MappingProxyType(
    {
        FakeScenario.TEXT_SUCCESS: FakeScenarioDefinition(content=_TEXT),
        FakeScenario.STRUCTURED_SUCCESS: FakeScenarioDefinition(
            structured=_STRUCTURED,
        ),
        FakeScenario.STREAM_SUCCESS: FakeScenarioDefinition(
            content=_TEXT,
            # C-4 strips whitespace at string boundaries. Keep spaces inside chunks so
            # validating each event cannot change the reconstructed deterministic text.
            stream_chunks=("Serviq deter", "ministic fake r", "esponse."),
        ),
        FakeScenario.TIMEOUT: FakeScenarioDefinition(
            error_code=GatewayErrorCode.PROVIDER_TIMEOUT,
            error_message="Deterministic fake provider timed out.",
        ),
        FakeScenario.RATE_LIMITED: FakeScenarioDefinition(
            error_code=GatewayErrorCode.PROVIDER_RATE_LIMITED,
            error_message="Deterministic fake provider was rate limited.",
        ),
        FakeScenario.UNAVAILABLE: FakeScenarioDefinition(
            error_code=GatewayErrorCode.PROVIDER_UNAVAILABLE,
            error_message="Deterministic fake provider is unavailable.",
        ),
        FakeScenario.AUTH_FAILED: FakeScenarioDefinition(
            error_code=GatewayErrorCode.PROVIDER_AUTH_FAILED,
            error_message="Deterministic fake provider authentication failed.",
        ),
        FakeScenario.MALFORMED_STRUCTURED: FakeScenarioDefinition(
            structured=_MALFORMED_STRUCTURED,
        ),
    }
)


class FakeLLMAdapter:
    """Scenario-injected adapter with zero network or provider-key dependency."""

    def __init__(self, scenario: FakeScenario = FakeScenario.TEXT_SUCCESS) -> None:
        self._scenario = scenario

    async def generate(
        self,
        request: GatewayRequest,
        context: AdapterContext,
    ) -> GatewayResponse:
        definition = FAKE_SCENARIOS[self._scenario]
        _raise_if_failure(definition)
        return GatewayResponse(
            content=definition.content,
            structured=definition.structured or {},
            provider=context.provider,
            upstreamModel=context.upstream_model,
            usage=GatewayUsage(inputTokens=42, outputTokens=7),
            finishReason="stop",
            requestId=_deterministic_request_id(request, context, self._scenario),
        )

    def stream(
        self,
        request: GatewayRequest,
        context: AdapterContext,
    ) -> AsyncIterator[GatewayStreamEvent]:
        async def events() -> AsyncIterator[GatewayStreamEvent]:
            definition = FAKE_SCENARIOS[self._scenario]
            _raise_if_failure(definition)
            if self._scenario is not FakeScenario.STREAM_SUCCESS:
                raise GatewayProviderError(
                    GatewayErrorCode.PROVIDER_INVALID_REQUEST,
                    "Selected fake scenario does not define streaming output.",
                )

            request_id = _deterministic_request_id(request, context, self._scenario)
            for chunk in definition.stream_chunks:
                yield GatewayStreamEvent(contentDelta=chunk)
            yield GatewayStreamEvent(
                finishReason="stop",
                usage=GatewayUsage(inputTokens=42, outputTokens=7),
                requestId=request_id,
            )

        return events()


def _raise_if_failure(definition: FakeScenarioDefinition) -> None:
    if definition.error_code is not None:
        assert definition.error_message is not None
        raise GatewayProviderError(definition.error_code, definition.error_message)


def _deterministic_request_id(
    request: GatewayRequest,
    context: AdapterContext,
    scenario: FakeScenario,
) -> str:
    canonical = {
        "request": request.model_dump(mode="json", by_alias=True),
        "provider": context.provider.value,
        "upstreamModel": context.upstream_model,
        "scenario": scenario.value,
    }
    encoded = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:24]
    return f"fake_{digest}"
