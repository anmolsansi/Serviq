"""OpenAI adapter behind Serviq's provider-neutral C-4 contract."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import cast

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    AsyncOpenAI,
    BadRequestError,
    NotFoundError,
    OpenAIError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)
from openai.types import ResponseFormatJSONSchema
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
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
)

OpenAIClientFactory = Callable[[str, float], AsyncOpenAI]
_JSON_OBJECT = TypeAdapter(dict[str, JsonValue])


def _default_client_factory(api_key: str, timeout_seconds: float) -> AsyncOpenAI:
    """Build a request-scoped official SDK client with retries disabled.

    Serviq owns retry/fallback policy above the provider adapter. Disabling SDK retries
    keeps the C-4 timeout budget predictable and prevents hidden duplicate calls.
    """

    return AsyncOpenAI(
        api_key=api_key,
        timeout=timeout_seconds,
        max_retries=0,
    )


class OpenAIAdapter:
    """Translate C-4 requests to the official OpenAI SDK and normalize the result."""

    def __init__(self, client_factory: OpenAIClientFactory = _default_client_factory) -> None:
        self._client_factory = client_factory

    async def generate(
        self,
        request: GatewayRequest,
        context: AdapterContext,
    ) -> GatewayResponse:
        if request.stream:
            raise _invalid_request("Use the streaming adapter path when stream=true.")
        client = self._client(request, context)
        messages = _messages(request)

        try:
            completion = await _create_completion(client, request, context, messages)
        except GatewayProviderError:
            raise
        except Exception as exc:
            raise _normalize_openai_error(exc) from None

        return _normalize_completion(completion, request, context)

    def stream(
        self,
        request: GatewayRequest,
        context: AdapterContext,
    ) -> AsyncIterator[GatewayStreamEvent]:
        async def events() -> AsyncIterator[GatewayStreamEvent]:
            if not request.stream:
                raise _invalid_request("Use the non-stream adapter path when stream=false.")
            client = self._client(request, context)
            messages = _messages(request)
            finish_reason: str | None = None
            usage: GatewayUsage | None = None
            request_id: str | None = None

            try:
                upstream = await _create_stream(client, request, context, messages)
                async for chunk in upstream:
                    if chunk.id:
                        request_id = chunk.id
                    if chunk.usage is not None:
                        usage = GatewayUsage(
                            inputTokens=chunk.usage.prompt_tokens,
                            outputTokens=chunk.usage.completion_tokens,
                        )
                    for choice in chunk.choices:
                        if choice.delta.content is not None:
                            yield GatewayStreamEvent(contentDelta=choice.delta.content)
                        if choice.finish_reason is not None:
                            finish_reason = str(choice.finish_reason)
            except GatewayProviderError:
                raise
            except Exception as exc:
                raise _normalize_openai_error(exc) from None

            if finish_reason is None and usage is None and request_id is None:
                raise GatewayProviderError(
                    GatewayErrorCode.PROVIDER_UNAVAILABLE,
                    "OpenAI stream ended without terminal metadata.",
                )
            yield GatewayStreamEvent(
                finishReason=finish_reason,
                usage=usage,
                requestId=request_id,
            )

        return events()

    def _client(self, request: GatewayRequest, context: AdapterContext) -> AsyncOpenAI:
        if context.provider is not GatewayProvider.OPENAI:
            raise _invalid_request("OpenAI adapter received a non-OpenAI provider context.")
        if context.api_key is None:
            raise GatewayProviderError(
                GatewayErrorCode.PROVIDER_AUTH_FAILED,
                "OpenAI credentials are unavailable.",
            )
        api_key = context.api_key.get_secret_value()
        if not api_key.strip():
            raise GatewayProviderError(
                GatewayErrorCode.PROVIDER_AUTH_FAILED,
                "OpenAI credentials are unavailable.",
            )
        return self._client_factory(api_key, request.timeout_ms / 1000.0)


async def _create_completion(
    client: AsyncOpenAI,
    request: GatewayRequest,
    context: AdapterContext,
    messages: list[ChatCompletionMessageParam],
) -> ChatCompletion:
    if request.response_schema:
        return await client.chat.completions.create(
            model=context.upstream_model,
            messages=messages,
            max_completion_tokens=request.max_output_tokens,
            response_format=_response_format(request),
            timeout=request.timeout_ms / 1000.0,
        )
    return await client.chat.completions.create(
        model=context.upstream_model,
        messages=messages,
        max_completion_tokens=request.max_output_tokens,
        timeout=request.timeout_ms / 1000.0,
    )


async def _create_stream(
    client: AsyncOpenAI,
    request: GatewayRequest,
    context: AdapterContext,
    messages: list[ChatCompletionMessageParam],
) -> AsyncIterator[ChatCompletionChunk]:
    if request.response_schema:
        return await client.chat.completions.create(
            model=context.upstream_model,
            messages=messages,
            max_completion_tokens=request.max_output_tokens,
            response_format=_response_format(request),
            stream=True,
            stream_options={"include_usage": True},
            timeout=request.timeout_ms / 1000.0,
        )
    return await client.chat.completions.create(
        model=context.upstream_model,
        messages=messages,
        max_completion_tokens=request.max_output_tokens,
        stream=True,
        stream_options={"include_usage": True},
        timeout=request.timeout_ms / 1000.0,
    )


def _messages(request: GatewayRequest) -> list[ChatCompletionMessageParam]:
    return [
        cast(
            ChatCompletionMessageParam,
            {"role": message.role.value, "content": message.content},
        )
        for message in request.messages
    ]


def _response_format(request: GatewayRequest) -> ResponseFormatJSONSchema:
    return cast(
        ResponseFormatJSONSchema,
        {
            "type": "json_schema",
            "json_schema": {
                "name": "serviq_response",
                "strict": True,
                "schema": request.response_schema,
            },
        },
    )


def _normalize_completion(
    completion: ChatCompletion,
    request: GatewayRequest,
    context: AdapterContext,
) -> GatewayResponse:
    if not completion.choices:
        raise GatewayProviderError(
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
            "OpenAI returned no completion choice.",
        )
    choice = completion.choices[0]
    content = choice.message.content
    structured: dict[str, JsonValue] = {}

    if request.response_schema:
        if content is None:
            raise GatewayProviderError(
                GatewayErrorCode.PROVIDER_UNAVAILABLE,
                "OpenAI returned no structured response content.",
            )
        try:
            structured = _JSON_OBJECT.validate_json(content)
        except ValidationError:
            raise GatewayProviderError(
                GatewayErrorCode.PROVIDER_UNAVAILABLE,
                "OpenAI returned malformed structured response content.",
            ) from None
        content = None
    elif content is None:
        raise GatewayProviderError(
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
            "OpenAI returned no response content.",
        )

    usage = completion.usage
    normalized_usage = GatewayUsage(
        inputTokens=usage.prompt_tokens if usage is not None else None,
        outputTokens=usage.completion_tokens if usage is not None else None,
    )
    return GatewayResponse(
        content=content,
        structured=structured,
        provider=GatewayProvider.OPENAI,
        upstreamModel=context.upstream_model,
        usage=normalized_usage,
        finishReason=str(choice.finish_reason),
        requestId=completion.id,
    )


def _normalize_openai_error(exc: Exception) -> GatewayProviderError:
    """Collapse every SDK failure into a safe C-4 category without provider detail."""

    if isinstance(exc, AuthenticationError | PermissionDeniedError):
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_AUTH_FAILED,
            "OpenAI authentication failed.",
        )
    if isinstance(exc, RateLimitError):
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_RATE_LIMITED,
            "OpenAI rate limit was reached.",
        )
    if isinstance(exc, APITimeoutError):
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_TIMEOUT,
            "OpenAI request timed out.",
        )
    if isinstance(exc, BadRequestError | NotFoundError | UnprocessableEntityError):
        return _invalid_request("OpenAI rejected the request.")
    if isinstance(exc, APIConnectionError):
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
            "OpenAI is unavailable.",
        )
    if isinstance(exc, APIStatusError):
        if exc.status_code == 401 or exc.status_code == 403:
            return GatewayProviderError(
                GatewayErrorCode.PROVIDER_AUTH_FAILED,
                "OpenAI authentication failed.",
            )
        if exc.status_code == 429:
            return GatewayProviderError(
                GatewayErrorCode.PROVIDER_RATE_LIMITED,
                "OpenAI rate limit was reached.",
            )
        if exc.status_code >= 500:
            return GatewayProviderError(
                GatewayErrorCode.PROVIDER_UNAVAILABLE,
                "OpenAI is unavailable.",
            )
        return _invalid_request("OpenAI rejected the request.")
    if isinstance(exc, OpenAIError):
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
            "OpenAI request failed.",
        )
    return GatewayProviderError(
        GatewayErrorCode.PROVIDER_UNAVAILABLE,
        "OpenAI request failed.",
    )


def _invalid_request(message: str) -> GatewayProviderError:
    return GatewayProviderError(GatewayErrorCode.PROVIDER_INVALID_REQUEST, message)
