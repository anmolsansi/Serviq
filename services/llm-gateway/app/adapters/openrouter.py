"""OpenRouter adapter behind Serviq's provider-neutral C-4 contract."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import suppress
from typing import cast

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    OpenAIError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionMessageParam,
    ChatCompletionStreamOptionsParam,
    completion_create_params,
)
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

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OpenRouterClientFactory = Callable[[str, float], AsyncOpenAI]
_JSON_OBJECT = TypeAdapter(dict[str, JsonValue])


def _default_client_factory(api_key: str, timeout_seconds: float) -> AsyncOpenAI:
    """Build a request-scoped OpenAI-compatible client pinned to OpenRouter.

    The destination is intentionally a code-owned constant. C-4 callers can choose a
    validated model configuration, but they cannot choose an arbitrary outbound URL.
    Serviq owns retries above the provider adapter, so SDK retries stay disabled.
    """

    return AsyncOpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        timeout=timeout_seconds,
        max_retries=0,
    )


class OpenRouterAdapter:
    """Translate C-4 requests to OpenRouter and normalize provider results."""

    def __init__(
        self,
        client_factory: OpenRouterClientFactory = _default_client_factory,
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
        messages = _messages(request)
        try:
            completion = await _create_completion(client, request, context, messages)
            return _normalize_completion(completion, request, context)
        except GatewayProviderError:
            raise
        except Exception as exc:
            raise _normalize_openrouter_error(exc) from None
        finally:
            await _close_client(client)

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
            structured_buffer: list[str] = []

            try:
                upstream = await _create_stream(client, request, context, messages)
                async for chunk in upstream:
                    embedded_error = _embedded_error(chunk)
                    if embedded_error is not None:
                        raise _normalize_embedded_openrouter_error(embedded_error)

                    if chunk.id:
                        request_id = chunk.id
                    if chunk.usage is not None:
                        usage = GatewayUsage(
                            inputTokens=chunk.usage.prompt_tokens,
                            outputTokens=chunk.usage.completion_tokens,
                        )

                    for choice in chunk.choices:
                        choice_error = _embedded_error(choice)
                        if choice_error is not None:
                            raise _normalize_embedded_openrouter_error(choice_error)

                        if choice.finish_reason is not None:
                            normalized_finish = str(choice.finish_reason)
                            if normalized_finish == "error":
                                raise GatewayProviderError(
                                    GatewayErrorCode.PROVIDER_UNAVAILABLE,
                                    "OpenRouter generation failed during streaming.",
                                )
                            finish_reason = normalized_finish

                        if choice.delta.content is None:
                            continue
                        if request.response_schema:
                            structured_buffer.append(choice.delta.content)
                        else:
                            yield GatewayStreamEvent(contentDelta=choice.delta.content)

                if finish_reason is None and usage is None and request_id is None:
                    raise GatewayProviderError(
                        GatewayErrorCode.PROVIDER_UNAVAILABLE,
                        "OpenRouter stream ended without terminal metadata.",
                    )

                if request.response_schema:
                    structured = _parse_structured("".join(structured_buffer))
                    yield GatewayStreamEvent(
                        structuredDelta=structured,
                        finishReason=finish_reason,
                        usage=usage,
                        requestId=request_id,
                    )
                else:
                    yield GatewayStreamEvent(
                        finishReason=finish_reason,
                        usage=usage,
                        requestId=request_id,
                    )
            except GatewayProviderError:
                raise
            except Exception as exc:
                raise _normalize_openrouter_error(exc) from None
            finally:
                await _close_client(client)

        return events()

    def _client(self, request: GatewayRequest, context: AdapterContext) -> AsyncOpenAI:
        if context.provider is not GatewayProvider.OPENROUTER:
            raise _invalid_request(
                "OpenRouter adapter received a non-OpenRouter provider context."
            )
        if context.api_key is None:
            raise GatewayProviderError(
                GatewayErrorCode.PROVIDER_AUTH_FAILED,
                "OpenRouter credentials are unavailable.",
            )
        api_key = context.api_key.get_secret_value()
        if not api_key.strip():
            raise GatewayProviderError(
                GatewayErrorCode.PROVIDER_AUTH_FAILED,
                "OpenRouter credentials are unavailable.",
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
            stream_options=_stream_options(),
            timeout=request.timeout_ms / 1000.0,
        )
    return await client.chat.completions.create(
        model=context.upstream_model,
        messages=messages,
        max_completion_tokens=request.max_output_tokens,
        stream=True,
        stream_options=_stream_options(),
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


def _response_format(request: GatewayRequest) -> completion_create_params.ResponseFormat:
    return cast(
        completion_create_params.ResponseFormat,
        {
            "type": "json_schema",
            "json_schema": {
                "name": "serviq_response",
                "strict": True,
                "schema": request.response_schema,
            },
        },
    )


def _stream_options() -> ChatCompletionStreamOptionsParam:
    return {"include_usage": True}


def _normalize_completion(
    completion: ChatCompletion,
    request: GatewayRequest,
    context: AdapterContext,
) -> GatewayResponse:
    if not completion.choices:
        raise GatewayProviderError(
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
            "OpenRouter returned no completion choice.",
        )

    choice = completion.choices[0]
    embedded_error = _embedded_error(choice)
    if embedded_error is not None:
        raise _normalize_embedded_openrouter_error(embedded_error)

    if str(choice.finish_reason) == "error":
        raise GatewayProviderError(
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
            "OpenRouter generation failed.",
        )

    content = choice.message.content
    structured: dict[str, JsonValue] = {}
    if request.response_schema:
        if content is None:
            raise GatewayProviderError(
                GatewayErrorCode.PROVIDER_UNAVAILABLE,
                "OpenRouter returned no structured response content.",
            )
        structured = _parse_structured(content)
        content = None
    elif content is None:
        raise GatewayProviderError(
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
            "OpenRouter returned no response content.",
        )

    usage = completion.usage
    return GatewayResponse(
        content=content,
        structured=structured,
        provider=GatewayProvider.OPENROUTER,
        upstreamModel=context.upstream_model,
        usage=GatewayUsage(
            inputTokens=usage.prompt_tokens if usage is not None else None,
            outputTokens=usage.completion_tokens if usage is not None else None,
        ),
        finishReason=str(choice.finish_reason),
        requestId=completion.id,
    )


def _parse_structured(text: str) -> dict[str, JsonValue]:
    if not text:
        raise GatewayProviderError(
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
            "OpenRouter returned no structured response content.",
        )
    try:
        return _JSON_OBJECT.validate_json(text)
    except ValidationError:
        raise GatewayProviderError(
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
            "OpenRouter returned malformed structured response content.",
        ) from None


def _embedded_error(value: object) -> object | None:
    direct = cast(object | None, getattr(value, "error", None))
    if direct is not None:
        return direct
    model_extra = cast(object | None, getattr(value, "model_extra", None))
    if isinstance(model_extra, Mapping):
        return cast(object | None, model_extra.get("error"))
    return None


def _error_field(value: object, field: str) -> object | None:
    if isinstance(value, Mapping):
        return cast(object | None, value.get(field))
    return cast(object | None, getattr(value, field, None))


def _normalize_embedded_openrouter_error(error: object) -> GatewayProviderError:
    """Normalize OpenRouter's in-band provider error without exposing raw details."""

    code_value = _error_field(error, "code")
    code = code_value if isinstance(code_value, int) else None
    metadata = _error_field(error, "metadata")
    error_type_value = _error_field(metadata, "error_type") if metadata is not None else None
    error_type = error_type_value if isinstance(error_type_value, str) else None

    if error_type in {"authentication", "permission_denied"}:
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_AUTH_FAILED,
            "OpenRouter authentication failed.",
        )
    if error_type == "rate_limit_exceeded":
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_RATE_LIMITED,
            "OpenRouter rate limit was reached.",
        )
    if error_type == "timeout":
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_TIMEOUT,
            "OpenRouter request timed out.",
        )
    if error_type in {"provider_overloaded", "provider_unavailable", "server", "unmapped"}:
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
            "OpenRouter is unavailable.",
        )
    if error_type is not None:
        return _invalid_request("OpenRouter rejected the request.")

    if code in {401, 403}:
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_AUTH_FAILED,
            "OpenRouter authentication failed.",
        )
    if code == 429:
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_RATE_LIMITED,
            "OpenRouter rate limit was reached.",
        )
    if code == 408:
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_TIMEOUT,
            "OpenRouter request timed out.",
        )
    if code is not None and code >= 500:
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
            "OpenRouter is unavailable.",
        )
    if code is not None and 400 <= code < 500:
        return _invalid_request("OpenRouter rejected the request.")
    return GatewayProviderError(
        GatewayErrorCode.PROVIDER_UNAVAILABLE,
        "OpenRouter request failed.",
    )


def _normalize_openrouter_error(exc: Exception) -> GatewayProviderError:
    """Collapse OpenAI-compatible SDK failures into safe C-4 provider errors."""

    if isinstance(exc, AuthenticationError | PermissionDeniedError):
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_AUTH_FAILED,
            "OpenRouter authentication failed.",
        )
    if isinstance(exc, RateLimitError):
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_RATE_LIMITED,
            "OpenRouter rate limit was reached.",
        )
    if isinstance(exc, APITimeoutError):
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_TIMEOUT,
            "OpenRouter request timed out.",
        )
    if isinstance(exc, BadRequestError | NotFoundError | UnprocessableEntityError):
        return _invalid_request("OpenRouter rejected the request.")
    if isinstance(exc, APIConnectionError):
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
            "OpenRouter is unavailable.",
        )
    if isinstance(exc, APIStatusError):
        if exc.status_code in {401, 403}:
            return GatewayProviderError(
                GatewayErrorCode.PROVIDER_AUTH_FAILED,
                "OpenRouter authentication failed.",
            )
        if exc.status_code == 429:
            return GatewayProviderError(
                GatewayErrorCode.PROVIDER_RATE_LIMITED,
                "OpenRouter rate limit was reached.",
            )
        if exc.status_code == 408:
            return GatewayProviderError(
                GatewayErrorCode.PROVIDER_TIMEOUT,
                "OpenRouter request timed out.",
            )
        if exc.status_code >= 500:
            return GatewayProviderError(
                GatewayErrorCode.PROVIDER_UNAVAILABLE,
                "OpenRouter is unavailable.",
            )
        return _invalid_request("OpenRouter rejected the request.")
    if isinstance(exc, OpenAIError):
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
            "OpenRouter request failed.",
        )
    return GatewayProviderError(
        GatewayErrorCode.PROVIDER_UNAVAILABLE,
        "OpenRouter request failed.",
    )


async def _close_client(client: AsyncOpenAI) -> None:
    with suppress(Exception):
        await client.close()


def _invalid_request(message: str) -> GatewayProviderError:
    return GatewayProviderError(GatewayErrorCode.PROVIDER_INVALID_REQUEST, message)
