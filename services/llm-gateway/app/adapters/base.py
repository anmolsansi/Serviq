"""Provider adapter boundary shared by deterministic and real implementations."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from pydantic import SecretStr

from app.schemas import GatewayProvider, GatewayRequest, GatewayResponse, GatewayStreamEvent


@dataclass(frozen=True, repr=False)
class AdapterContext:
    """Server-resolved values passed to an adapter after routing/secret lookup."""

    provider: GatewayProvider
    upstream_model: str
    api_key: SecretStr | None = None

    def __post_init__(self) -> None:
        if not self.upstream_model.strip():
            raise ValueError("upstream_model must not be blank")

    def __repr__(self) -> str:
        return (
            "AdapterContext("
            f"provider={self.provider.value!r}, "
            f"upstream_model={self.upstream_model!r}, "
            "api_key=<redacted>)"
        )


class LLMAdapter(Protocol):
    """Minimal interface every C-4 provider implementation must satisfy."""

    async def generate(
        self,
        request: GatewayRequest,
        context: AdapterContext,
    ) -> GatewayResponse: ...

    def stream(
        self,
        request: GatewayRequest,
        context: AdapterContext,
    ) -> AsyncIterator[GatewayStreamEvent]: ...
