"""Serviq-owned provider-neutral Contract C-4 models.

This module is intentionally independent of every provider SDK. Adapters translate
between provider objects and these models at the adapter boundary.
"""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

MAX_OUTPUT_TOKENS = 1_500
MAX_TIMEOUT_MS = 20_000


class GatewayPurpose(StrEnum):
    CLASSIFICATION = "classification"
    GENERATION = "generation"
    EVALUATION = "evaluation"


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class GatewayProvider(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OPENROUTER = "openrouter"


class GatewayErrorCode(StrEnum):
    PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMITED"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_INVALID_REQUEST = "PROVIDER_INVALID_REQUEST"
    PROVIDER_AUTH_FAILED = "PROVIDER_AUTH_FAILED"


class _StrictContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class _ProviderOutputContractModel(BaseModel):
    """Strict output model that must not mutate provider-generated text."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=False,
    )


class GatewayMessage(_StrictContractModel):
    role: MessageRole
    content: str = Field(min_length=1)


class GatewayRequest(_StrictContractModel):
    tenant_id: UUID = Field(alias="tenantId")
    model_alias: str = Field(alias="modelAlias", min_length=1)
    purpose: GatewayPurpose
    messages: list[GatewayMessage] = Field(min_length=1)
    response_schema: dict[str, JsonValue] = Field(
        default_factory=dict,
        alias="responseSchema",
    )
    max_output_tokens: int = Field(
        default=MAX_OUTPUT_TOKENS,
        alias="maxOutputTokens",
        ge=1,
        le=MAX_OUTPUT_TOKENS,
    )
    timeout_ms: int = Field(
        default=MAX_TIMEOUT_MS,
        alias="timeoutMs",
        ge=1,
        le=MAX_TIMEOUT_MS,
    )
    stream: bool = False
    correlation_id: str = Field(alias="correlationId", min_length=1)


class GatewayUsage(_StrictContractModel):
    input_tokens: int | None = Field(default=None, alias="inputTokens", ge=0)
    output_tokens: int | None = Field(default=None, alias="outputTokens", ge=0)


class GatewayResponse(_ProviderOutputContractModel):
    content: str | None
    structured: dict[str, JsonValue]
    provider: GatewayProvider
    upstream_model: str = Field(alias="upstreamModel", min_length=1)
    usage: GatewayUsage
    finish_reason: str = Field(alias="finishReason", min_length=1)
    request_id: str | None = Field(alias="requestId")


class GatewayStreamEvent(_ProviderOutputContractModel):
    """Provider-neutral incremental event used only when `request.stream` is true.

    Contract C-4 freezes the request flag and normalized response semantics but does
    not expose a provider SDK chunk type. This event carries only incremental Serviq
    data needed to reconstruct a response: content/structured deltas and optional
    terminal metadata.
    """

    content_delta: str | None = Field(default=None, alias="contentDelta")
    structured_delta: dict[str, JsonValue] | None = Field(
        default=None,
        alias="structuredDelta",
    )
    finish_reason: str | None = Field(default=None, alias="finishReason")
    usage: GatewayUsage | None = None
    request_id: str | None = Field(default=None, alias="requestId")

    @model_validator(mode="after")
    def require_event_payload(self) -> GatewayStreamEvent:
        if (
            self.content_delta is None
            and self.structured_delta is None
            and self.finish_reason is None
            and self.usage is None
            and self.request_id is None
        ):
            raise ValueError("stream event must carry a delta or terminal metadata")
        return self


class GatewayError(_StrictContractModel):
    code: GatewayErrorCode
    message: str = Field(min_length=1)


class GatewayProviderError(RuntimeError):
    """Normalized adapter failure with no provider-SDK exception in its public shape."""

    def __init__(self, code: GatewayErrorCode, message: str) -> None:
        self.error = GatewayError(code=code, message=message)
        super().__init__(message)

    @property
    def code(self) -> GatewayErrorCode:
        return self.error.code
