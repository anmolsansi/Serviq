"""Anthropic adapter behind Serviq's provider-neutral C-4 contract."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import cast

from anthropic import (
    AnthropicError,
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)
from anthropic.types import Message, MessageParam, OutputConfigParam, RawMessageStreamEvent
from pydantic import JsonValue, TypeAdapter, ValidationError

from app.adapters.base import AdapterContext
from app.schemas import (
    GatewayErrorCode,
    GatewayProvider,
    GatewayProviderError,
    GatewayRequest,
    GatewayResponse,
    GatewayStreamEvent,
    GatewayUsage,
    MessageRole,
)

AnthropicClientFactory = Callable[[str, float], AsyncAnthropic]
_JSON_OBJECT = TypeAdapter(dict[str, JsonValue])


def _default_client_factory(api_key: str, timeout_seconds: float) -> AsyncAnthropic:
    """Build a request-scoped official SDK client with hidden retries disabled."""

    return AsyncAnthropic(
        api_key=api_key,
        timeout=timeout_seconds,
        max_retries=0,
    )


class AnthropicAdapter:
    """Translate C-4 requests to Anthropic Messages API calls and back."""

    def __init__(
        self,
        client_factory: AnthropicClientFactory = _default_client_factory,
    ) -> None:
        self._client_factory = client_factory

    async def generate(
        self,
        request: GatewayRequest,
        context: AdapterContext,
    ) -> GatewayResponse:
        if request.stream:
            raise _invalid_request("Use the streaming adapter path when stream=true.")
        client = self._client(request, context)
        system, messages = _translate_messages(request)

        try:
            message = await _create_message(client, request, context, system, messages)
        except GatewayProviderError:
            raise
        except Exception as exc:
            raise _normalize_anthropic_error(exc) from None

        return _normalize_message(message, request, context)

    def stream(
        self,
        request: GatewayRequest,
        context: AdapterContext,
    ) -> AsyncIterator[GatewayStreamEvent]:
        async def events() -> AsyncIterator[GatewayStreamEvent]:
            if not request.stream:
                raise _invalid_request("Use the non-stream adapter path when stream=false.")
            client = self._client(request, context)
            system, messages = _translate_messages(request)
            request_id: str | None = None
            finish_reason: str | None = None
            input_tokens: int | None = None
            output_tokens: int | None = None
            structured_buffer: list[str] = []

            try:
                upstream = await _create_stream(client, request, context, system, messages)
                async for event in upstream:
                    if event.type == "message_start":
                        request_id = event.message.id
                        input_tokens = event.message.usage.input_tokens
                    elif event.type == "content_block_delta" and event.delta.type == "text_delta":
                        if request.response_schema:
                            structured_buffer.append(event.delta.text)
                        else:
                            yield GatewayStreamEvent(contentDelta=event.delta.text)
                    elif event.type == "message_delta":
                        if event.delta.stop_reason is not None:
                            finish_reason = str(event.delta.stop_reason)
                        if event.usage.input_tokens is not None:
                            input_tokens = event.usage.input_tokens
                        output_tokens = event.usage.output_tokens
            except GatewayProviderError:
                raise
            except Exception as exc:
                raise _normalize_anthropic_error(exc) from None

            if request.response_schema:
                structured_text = "".join(structured_buffer)
                try:
                    structured = _JSON_OBJECT.validate_json(structured_text)
                except ValidationError:
                    raise GatewayProviderError(
                        GatewayErrorCode.PROVIDER_UNAVAILABLE,
                        "Anthropic returned malformed structured response content.",
                    ) from None
                yield GatewayStreamEvent(structuredDelta=structured)

            if finish_reason is None or request_id is None:
                raise GatewayProviderError(
                    GatewayErrorCode.PROVIDER_UNAVAILABLE,
                    "Anthropic stream ended without terminal metadata.",
                )
            yield GatewayStreamEvent(
                finishReason=finish_reason,
                usage=GatewayUsage(
                    inputTokens=input_tokens,
                    outputTokens=output_tokens,
                ),
                requestId=request_id,
            )

        return events()

    def _client(self, request: GatewayRequest, context: AdapterContext) -> AsyncAnthropic:
        if context.provider is not GatewayProvider.ANTHROPIC:
            raise _invalid_request("Anthropic adapter received a non-Anthropic provider context.")
        if context.api_key is None:
            raise GatewayProviderError(
                GatewayErrorCode.PROVIDER_AUTH_FAILED,
                "Anthropic credentials are unavailable.",
            )
        api_key = context.api_key.get_secret_value()
        if not api_key.strip():
            raise GatewayProviderError(
                GatewayErrorCode.PROVIDER_AUTH_FAILED,
                "Anthropic credentials are unavailable.",
            )
        return self._client_factory(api_key, request.timeout_ms / 1000.0)


async def _create_message(
    client: AsyncAnthropic,
    request: GatewayRequest,
    context: AdapterContext,
    system: str | None,
    messages: list[MessageParam],
) -> Message:
    output_config = _output_config(request) if request.response_schema else None
    timeout = request.timeout_ms / 1000.0

    if system is not None and output_config is not None:
        return await client.messages.create(
            model=context.upstream_model,
            max_tokens=request.max_output_tokens,
            messages=messages,
            system=system,
            output_config=output_config,
            timeout=timeout,
        )
    if system is not None:
        return await client.messages.create(
            model=context.upstream_model,
            max_tokens=request.max_output_tokens,
            messages=messages,
            system=system,
            timeout=timeout,
        )
    if output_config is not None:
        return await client.messages.create(
            model=context.upstream_model,
            max_tokens=request.max_output_tokens,
            messages=messages,
            output_config=output_config,
            timeout=timeout,
        )
    return await client.messages.create(
        model=context.upstream_model,
        max_tokens=request.max_output_tokens,
        messages=messages,
        timeout=timeout,
    )


async def _create_stream(
    client: AsyncAnthropic,
    request: GatewayRequest,
    context: AdapterContext,
    system: str | None,
    messages: list[MessageParam],
) -> AsyncIterator[RawMessageStreamEvent]:
    output_config = _output_config(request) if request.response_schema else None
    timeout = request.timeout_ms / 1000.0

    if system is not None and output_config is not None:
        return await client.messages.create(
            model=context.upstream_model,
            max_tokens=request.max_output_tokens,
            messages=messages,
            system=system,
            output_config=output_config,
            stream=True,
            timeout=timeout,
        )
    if system is not None:
        return await client.messages.create(
            model=context.upstream_model,
            max_tokens=request.max_output_tokens,
            messages=messages,
            system=system,
            stream=True,
            timeout=timeout,
        )
    if output_config is not None:
        return await client.messages.create(
            model=context.upstream_model,
            max_tokens=request.max_output_tokens,
            messages=messages,
            output_config=output_config,
            stream=True,
            timeout=timeout,
        )
    return await client.messages.create(
        model=context.upstream_model,
        max_tokens=request.max_output_tokens,
        messages=messages,
        stream=True,
        timeout=timeout,
    )


def _translate_messages(request: GatewayRequest) -> tuple[str | None, list[MessageParam]]:
    """Move only leading C-4 system messages into Anthropic's top-level system field."""

    systems: list[str] = []
    messages: list[MessageParam] = []
    conversation_started = False

    for message in request.messages:
        if message.role is MessageRole.SYSTEM:
            if conversation_started:
                raise _invalid_request(
                    "Anthropic requires system messages before conversational messages."
                )
            systems.append(message.content)
            continue

        conversation_started = True
        messages.append(
            cast(
                MessageParam,
                {"role": message.role.value, "content": message.content},
            )
        )

    if not messages:
        raise _invalid_request("Anthropic requires at least one user or assistant message.")

    system = "\n\n".join(systems) if systems else None
    return system, messages


def _output_config(request: GatewayRequest) -> OutputConfigParam:
    return cast(
        OutputConfigParam,
        {
            "format": {
                "type": "json_schema",
                "schema": request.response_schema,
            }
        },
    )


def _normalize_message(
    message: Message,
    request: GatewayRequest,
    context: AdapterContext,
) -> GatewayResponse:
    text = _message_text(message)
    structured: dict[str, JsonValue] = {}
    content: str | None = text

    if request.response_schema:
        try:
            structured = _JSON_OBJECT.validate_json(text)
        except ValidationError:
            raise GatewayProviderError(
                GatewayErrorCode.PROVIDER_UNAVAILABLE,
                "Anthropic returned malformed structured response content.",
            ) from None
        content = None

    if message.stop_reason is None:
        raise GatewayProviderError(
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
            "Anthropic returned no finish reason.",
        )

    return GatewayResponse(
        content=content,
        structured=structured,
        provider=GatewayProvider.ANTHROPIC,
        upstreamModel=context.upstream_model,
        usage=GatewayUsage(
            inputTokens=message.usage.input_tokens,
            outputTokens=message.usage.output_tokens,
        ),
        finishReason=str(message.stop_reason),
        requestId=message.id,
    )


def _message_text(message: Message) -> str:
    text_parts: list[str] = []
    for block in message.content:
        if block.type != "text":
            raise GatewayProviderError(
                GatewayErrorCode.PROVIDER_UNAVAILABLE,
                "Anthropic returned an unsupported response content block.",
            )
        text_parts.append(block.text)
    if not text_parts:
        raise GatewayProviderError(
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
            "Anthropic returned no response content.",
        )
    return "".join(text_parts)


def _normalize_anthropic_error(exc: Exception) -> GatewayProviderError:
    """Collapse Anthropic SDK failures into fixed provider-neutral C-4 errors."""

    if isinstance(exc, AuthenticationError | PermissionDeniedError):
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_AUTH_FAILED,
            "Anthropic authentication failed.",
        )
    if isinstance(exc, RateLimitError):
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_RATE_LIMITED,
            "Anthropic rate limit was reached.",
        )
    if isinstance(exc, APITimeoutError):
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_TIMEOUT,
            "Anthropic request timed out.",
        )
    if isinstance(exc, BadRequestError | NotFoundError | ConflictError | UnprocessableEntityError):
        return _invalid_request("Anthropic rejected the request.")
    if isinstance(exc, APIConnectionError):
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
            "Anthropic is unavailable.",
        )
    if isinstance(exc, APIStatusError):
        if exc.status_code == 401 or exc.status_code == 403:
            return GatewayProviderError(
                GatewayErrorCode.PROVIDER_AUTH_FAILED,
                "Anthropic authentication failed.",
            )
        if exc.status_code == 429:
            return GatewayProviderError(
                GatewayErrorCode.PROVIDER_RATE_LIMITED,
                "Anthropic rate limit was reached.",
            )
        if 400 <= exc.status_code < 500:
            return _invalid_request("Anthropic rejected the request.")
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
            "Anthropic is unavailable.",
        )
    if isinstance(exc, AnthropicError):
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
            "Anthropic request failed.",
        )
    return GatewayProviderError(
        GatewayErrorCode.PROVIDER_UNAVAILABLE,
        "Anthropic request failed.",
    )


def _invalid_request(message: str) -> GatewayProviderError:
    return GatewayProviderError(GatewayErrorCode.PROVIDER_INVALID_REQUEST, message)
