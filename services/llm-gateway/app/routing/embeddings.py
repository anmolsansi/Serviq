"""Private C-4 embedding path for the frozen V1 embedding profile."""

from fastapi import APIRouter, Header, HTTPException, status

from app.adapters import AdapterContext, FakeLLMAdapter
from app.connectivity import _require_internal_token
from app.schemas import (
    GatewayEmbeddingRequest,
    GatewayEmbeddingResponse,
    GatewayErrorCode,
    GatewayProvider,
    GatewayProviderError,
)

EMBEDDING_MODEL_ALIAS = "serviq-embedding-v1"

router = APIRouter(prefix="/internal/v1", tags=["internal-embeddings"])


def _resolve_adapter(model_alias: str) -> tuple[FakeLLMAdapter, AdapterContext]:
    """Resolve the only architect-frozen V1 embedding profile."""

    if model_alias != EMBEDDING_MODEL_ALIAS:
        raise GatewayProviderError(
            GatewayErrorCode.PROVIDER_UNAVAILABLE,
            "Embedding profile is unavailable.",
        )
    return FakeLLMAdapter(), AdapterContext(
        provider=GatewayProvider.OPENAI,
        upstream_model="serviq-fake-v1",
        api_key=None,
    )


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
    """Generate deterministic V1 embeddings behind the existing internal auth boundary."""

    _require_internal_token(authorization)

    try:
        adapter, context = _resolve_adapter(request.model_alias)
        response = await adapter.embed(request, context)
        if len(response.embeddings) != len(request.inputs):
            raise GatewayProviderError(
                GatewayErrorCode.PROVIDER_UNAVAILABLE,
                "Embedding provider returned an invalid batch response.",
            )
        return response
    except GatewayProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": error.code, "message": str(error)},
        ) from None
