"""Internal embedding generation path."""

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import SecretStr

from app.adapters import AdapterContext, FakeLLMAdapter, LLMAdapter
from app.connectivity import _require_internal_token
from app.schemas import (
    GatewayEmbeddingRequest,
    GatewayEmbeddingResponse,
    GatewayErrorCode,
    GatewayProvider,
    GatewayProviderError,
)

router = APIRouter(prefix="/internal/v1", tags=["embeddings"])


def _resolve_adapter(model_alias: str) -> tuple[LLMAdapter, AdapterContext]:
    """Stub resolver. In V1.4+ this will query the control plane for tenant policies."""
    if model_alias == "serviq-embedding-v1" or model_alias == "fake-embedding":
        return FakeLLMAdapter(), AdapterContext(
            provider=GatewayProvider.OPENAI,  # FAKE uses any provider context
            upstream_model="serviq-fake-v1",
            api_key=SecretStr("fake-key-never-real"),
        )
    raise GatewayProviderError(GatewayErrorCode.PROVIDER_UNAVAILABLE, "No embedding route found")


@router.post(
    "/embeddings",
    status_code=status.HTTP_200_OK,
    response_model=GatewayEmbeddingResponse,
    response_model_exclude_none=True,
    response_model_by_alias=True,
)
async def generate_embeddings(
    request: GatewayEmbeddingRequest,
    authorization: str | None = Header(default=None),
) -> GatewayEmbeddingResponse:
    """Generate deterministic or provider embeddings."""
    _require_internal_token(authorization)

    try:
        adapter, context = _resolve_adapter(request.model_alias)
        return await adapter.embed(request, context)
    except GatewayProviderError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": e.code, "message": str(e)},
        ) from None
