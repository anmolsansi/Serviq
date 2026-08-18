"""Gemini adapter behind Serviq's provider-neutral C-4 contract."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from enum import Enum

import httpx
from google import genai
from google.genai import errors, types
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

GeminiClientFactory = Callable[[str], genai.Client]
_JSON_OBJECT = TypeAdapter(dict[str, JsonValue])


def _default_client_factory(api_key: str) -> genai.Client:
    """Build a request-scoped official Gemini Developer API client.

    Timeout and retry settings are attached to each generation request so the
    already-validated C-4 budget stays authoritative. No base URL, project, location,
    or enterprise/Vertex routing can be supplied through the gateway request.
    """

    return genai.Client(api_key=api_key)


class GeminiAdapter:
    """Translate C-4 requests to Google Gen AI SDK calls and normalize the result."""

    def __init__(self, client_factory: GeminiClientFactory = _default_client_factory) -> None:
        self._client_factory = client_factory

    async def generate(
        self,
        request: GatewayRequest,
        context: AdapterContext,
    ) -> GatewayResponse:
        if request.stream:
            raise _invalid_request("Use the streaming adapter path when stream=true.")

        client = self._client(context)
        system_instruction, contents = _translate_messages(request)
        config = _generation_config(request, system_instruction)

        try:
            response = await client.aio.models.generate_content(
                model=context.upstream_model,
                contents=contents,
                config=config,
            )
            return _normalize_response(response, request, context)
        except GatewayProviderError:
            raise
        except Exception as exc:
            raise _normalize_gemini_error(exc) from None
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

            client = self._client(context)
            system_instruction, contents = _translate_messages(request)
            config = _generation_config(request, system_instruction)
            finish_reason: str | None = None
            usage: GatewayUsage | None = None
            request_id: str | None = None
            structured_text: list[str] = []

            try:
                upstream = await client.aio.models.generate_content_stream(
                    model=context.upstream_model,
                    contents=contents,
                    config=config,
                )
                async for chunk in upstream:
                    if chunk.response_id:
                        request_id = chunk.response_id
                    chunk_usage = _usage(chunk)
                    if chunk_usage is not None:
                        usage = chunk_usage
                    chunk_finish = _response_finish_reason(chunk)
                    if chunk_finish is not None:
                        finish_reason = chunk_finish

                    text = chunk.text
                    if text is None:
                        continue
                    if request.response_schema:
                        structured_text.append(text)
                    else:
                        yield GatewayStreamEvent(contentDelta=text)

                if finish_reason is None and usage is None and request_id is None:
                    raise GatewayProviderError(
                        GatewayErrorCode.PROVIDER_UNAVAILABLE,
                        "Gemini stream ended without terminal metadata.",
                    )

                if request.response_schema:
                    structured = _parse_structured("".join(structured_text))
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
                raise _normalize_gemini_error(exc) from None
            finally:
                await _close_client(client)

        return events()

    def _client(self, context: AdapterContext) -> genai.Client:
        if context.provider is not GatewayProvider.GEMINI:
            raise _invalid_request("Gemini adapter received a non-Gemini provider context.")
        if context.api_key is None:
            raise GatewayProviderError(
                GatewayErrorCode.PROVIDER_AUTH_FAILED,
                "Gemini credentials are unavailable.",
            )
        api_key = context.api_key.get_secret_value()
        if not api_key.strip():
            raise GatewayProviderError(
                GatewayErrorCode.PROVIDER_AUTH_FAILED,
                "Gemini credentials are unavailable.",
            )
        return self._client_factory(api_key)


def _translate_messages(request: GatewayRequest) -> tuple[str | None, list[types.Content]]:
    system_messages: list[str] = []
    contents: list[types.Content] = []
    conversation_started = False

    for message in request.messages:
        if message.role is MessageRole.SYSTEM:
            if conversation_started:
                raise _invalid_request(
                    "Gemini requires system messages before conversation messages."
                )
            system_messages.append(message.content)
            continue

        conversation_started = True
        role = "user" if message.role is MessageRole.USER else "model"
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part.from_text(text=message.content)],
            )
        )

    if not contents:
        raise _invalid_request("Gemini requires at least one conversation message.")

    system_instruction = "\n\n".join(system_messages) if system_messages else None
    return system_instruction, contents


def _generation_config(
    request: GatewayRequest,
    system_instruction: str | None,
) -> types.GenerateContentConfig:
    http_options = types.HttpOptions(
        timeout=request.timeout_ms,
        retry_options=types.HttpRetryOptions(attempts=1),
    )
    if request.response_schema:
        return types.GenerateContentConfig(
            system_instruction=system_instruction,
            max_output_tokens=request.max_output_tokens,
            response_mime_type="application/json",
            response_json_schema=request.response_schema,
            http_options=http_options,
        )
    return types.GenerateContentConfig(
        system_instruction=system_instruction,
        max_output_tokens=request.max_output_tokens,
        http_options=http_options,
    )


def _normalize_response(
    response: types.GenerateContentResponse,
    request: GatewayRequest,
    context: AdapterContext,
) -> GatewayResponse:
    finish_reason = _response_finish_reason(response)
    if finish_reason is None:
        raise GatewayProviderError(
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
            "Gemini returned no finish reason.",
        )

    text = response.text
    structured: dict[str, JsonValue] = {}
    if request.response_schema:
        if text is None:
            raise GatewayProviderError(
                GatewayErrorCode.PROVIDER_UNAVAILABLE,
                "Gemini returned no structured response content.",
            )
        structured = _parse_structured(text)
        content: str | None = None
    else:
        if text is None:
            raise GatewayProviderError(
                GatewayErrorCode.PROVIDER_UNAVAILABLE,
                "Gemini returned no response content.",
            )
        content = text

    return GatewayResponse(
        content=content,
        structured=structured,
        provider=GatewayProvider.GEMINI,
        upstreamModel=context.upstream_model,
        usage=_usage(response) or GatewayUsage(),
        finishReason=finish_reason,
        requestId=response.response_id,
    )


def _parse_structured(text: str) -> dict[str, JsonValue]:
    if not text:
        raise GatewayProviderError(
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
            "Gemini returned no structured response content.",
        )
    try:
        return _JSON_OBJECT.validate_json(text)
    except ValidationError:
        raise GatewayProviderError(
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
            "Gemini returned malformed structured response content.",
        ) from None


def _usage(response: types.GenerateContentResponse) -> GatewayUsage | None:
    metadata = response.usage_metadata
    if metadata is None:
        return None
    return GatewayUsage(
        inputTokens=metadata.prompt_token_count,
        outputTokens=metadata.candidates_token_count,
    )


def _response_finish_reason(response: types.GenerateContentResponse) -> str | None:
    if not response.candidates:
        return None
    return _finish_reason(response.candidates[0].finish_reason)


def _finish_reason(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, Enum) and isinstance(value.value, str):
        return value.value
    return str(value)


def _normalize_gemini_error(exc: Exception) -> GatewayProviderError:
    """Collapse SDK/transport failures into safe C-4 errors without provider detail."""

    if isinstance(exc, httpx.TimeoutException | TimeoutError):
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_TIMEOUT,
            "Gemini request timed out.",
        )
    if isinstance(exc, httpx.TransportError):
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
            "Gemini is unavailable.",
        )
    if isinstance(exc, errors.APIError):
        if exc.code in {401, 403}:
            return GatewayProviderError(
                GatewayErrorCode.PROVIDER_AUTH_FAILED,
                "Gemini authentication failed.",
            )
        if exc.code == 429:
            return GatewayProviderError(
                GatewayErrorCode.PROVIDER_RATE_LIMITED,
                "Gemini rate limit was reached.",
            )
        if exc.code == 408:
            return GatewayProviderError(
                GatewayErrorCode.PROVIDER_TIMEOUT,
                "Gemini request timed out.",
            )
        if 400 <= exc.code < 500:
            return _invalid_request("Gemini rejected the request.")
        if exc.code >= 500:
            return GatewayProviderError(
                GatewayErrorCode.PROVIDER_UNAVAILABLE,
                "Gemini is unavailable.",
            )
        return GatewayProviderError(
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
            "Gemini request failed.",
        )
    if isinstance(exc, ValueError | TypeError):
        return _invalid_request("Gemini rejected the request.")
    return GatewayProviderError(
        GatewayErrorCode.PROVIDER_UNAVAILABLE,
        "Gemini request failed.",
    )


async def _close_client(client: genai.Client) -> None:
    """Release request-scoped SDK resources without changing the normalized outcome."""

    try:
        await client.aio.aclose()
    except Exception:
        pass
    try:
        client.close()
    except Exception:
        pass


def _invalid_request(message: str) -> GatewayProviderError:
    return GatewayProviderError(GatewayErrorCode.PROVIDER_INVALID_REQUEST, message)
