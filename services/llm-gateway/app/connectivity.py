"""Private, bounded provider connectivity control path for OPE-298."""

from __future__ import annotations

import hmac
import os
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from app.adapters import (
    AdapterContext,
    AnthropicAdapter,
    GeminiAdapter,
    LLMAdapter,
    OpenAIAdapter,
    OpenRouterAdapter,
)
from app.schemas import (
    GatewayErrorCode,
    GatewayMessage,
    GatewayProvider,
    GatewayProviderError,
    GatewayPurpose,
    GatewayRequest,
    MessageRole,
)

CONNECTIVITY_TEST_MODELS: dict[GatewayProvider, str] = {
    GatewayProvider.OPENAI: "gpt-5-nano",
    GatewayProvider.ANTHROPIC: "claude-haiku-4-5-20251001",
    GatewayProvider.GEMINI: "gemini-3.5-flash-lite",
    GatewayProvider.OPENROUTER: "openrouter/free",
}
CONNECTIVITY_TEST_PROMPT = "Reply with OK."
CONNECTIVITY_TEST_MAX_OUTPUT_TOKENS = 4
CONNECTIVITY_TEST_TIMEOUT_MS = 5_000
_INTERNAL_TOKEN_ENV = "LLM_GATEWAY_INTERNAL_TOKEN"

router = APIRouter(prefix="/internal/v1", tags=["internal-provider-connectivity"])


class ProviderConnectivityRequest(BaseModel):
    """Private server-to-server request with no caller-controlled model or prompt."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    tenant_id: UUID = Field(alias="tenantId")
    provider: GatewayProvider
    api_key: SecretStr = Field(alias="apiKey", min_length=1, max_length=4096)
    correlation_id: str = Field(alias="correlationId", min_length=1, max_length=256)


class ProviderConnectivityResponse(BaseModel):
    """Safe connectivity outcome; generated provider content is intentionally absent."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    ok: bool
    error_code: GatewayErrorCode | None = Field(default=None, alias="errorCode")

    @model_validator(mode="after")
    def require_consistent_outcome(self) -> ProviderConnectivityResponse:
        if self.ok and self.error_code is not None:
            raise ValueError("successful connectivity result cannot contain errorCode")
        if not self.ok and self.error_code is None:
            raise ValueError("failed connectivity result requires errorCode")
        return self


def _require_internal_token(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    expected = os.getenv(_INTERNAL_TOKEN_ENV, "")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "INTERNAL_GATEWAY_AUTH_UNAVAILABLE", "message": "Gateway unavailable."},
        )

    prefix = "Bearer "
    supplied = authorization[len(prefix) :] if authorization and authorization.startswith(prefix) else ""
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Unauthorized."},
        )


def _adapter_for(provider: GatewayProvider) -> LLMAdapter:
    if provider is GatewayProvider.OPENAI:
        return OpenAIAdapter()
    if provider is GatewayProvider.ANTHROPIC:
        return AnthropicAdapter()
    if provider is GatewayProvider.GEMINI:
        return GeminiAdapter()
    if provider is GatewayProvider.OPENROUTER:
        return OpenRouterAdapter()
    raise AssertionError("GatewayProvider enum is not exhaustively handled")


async def run_connectivity_test(
    request: ProviderConnectivityRequest,
    *,
    adapter: LLMAdapter | None = None,
) -> ProviderConnectivityResponse:
    """Execute one fixed non-stream provider request and discard generated content."""

    gateway_request = GatewayRequest(
        tenantId=request.tenant_id,
        modelAlias="__serviq_provider_connectivity_test__",
        purpose=GatewayPurpose.CLASSIFICATION,
        messages=[GatewayMessage(role=MessageRole.USER, content=CONNECTIVITY_TEST_PROMPT)],
        responseSchema={},
        maxOutputTokens=CONNECTIVITY_TEST_MAX_OUTPUT_TOKENS,
        timeoutMs=CONNECTIVITY_TEST_TIMEOUT_MS,
        stream=False,
        correlationId=request.correlation_id,
    )
    context = AdapterContext(
        provider=request.provider,
        upstream_model=CONNECTIVITY_TEST_MODELS[request.provider],
        api_key=request.api_key,
    )

    target = _adapter_for(request.provider) if adapter is None else adapter
    try:
        await target.generate(gateway_request, context)
    except GatewayProviderError as error:
        return ProviderConnectivityResponse(ok=False, errorCode=error.code)

    return ProviderConnectivityResponse(ok=True, errorCode=None)


@router.post(
    "/provider-connectivity-test",
    response_model=ProviderConnectivityResponse,
    dependencies=[],
)
async def provider_connectivity_test(
    request: ProviderConnectivityRequest,
    _: Annotated[None, Header(alias="x-serviq-internal-auth-placeholder")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> ProviderConnectivityResponse:
    """Private endpoint used only by Serviq API provider-management code."""

    del _
    _require_internal_token(authorization)
    return await run_connectivity_test(request)
