"""Tenant-scoped provider connection routes."""

from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api import SuccessEnvelope
from app.core.database import get_database_session
from app.core.principal import require_tenant_id, require_workforce_user_id
from app.core.rate_limits import ProviderTestRateLimiter, get_provider_test_rate_limiter
from app.core.secret_store import TenantSecretStore, build_local_secret_store
from app.modules.providers.errors import (
    ProviderConflictError,
    ProviderForbiddenError,
    ProviderNotFoundError,
    ProviderReferencedError,
    ProviderSecretCleanupError,
    ProviderTestRateLimitedError,
    ProviderTestStaleError,
    ProviderTestUnavailableError,
)
from app.modules.providers.gateway import (
    ProviderConnectivityGateway,
    build_provider_connectivity_gateway,
)
from app.modules.providers.schemas import (
    ProviderConnectivityView,
    ProviderCreateRequest,
    ProviderUpdateRequest,
    ProviderView,
)
from app.modules.providers.service import (
    create_provider,
    delete_provider,
    get_provider,
    list_providers,
    test_provider_connectivity,
    update_provider,
)

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
WorkforceUserId = Annotated[UUID, Depends(require_workforce_user_id)]
TenantId = Annotated[UUID, Depends(require_tenant_id)]


def get_provider_secret_store(request: Request) -> TenantSecretStore:
    """Resolve the app-owned store or build the local V1 adapter."""

    configured = getattr(request.app.state, "secret_store", None)
    if configured is not None:
        return cast(TenantSecretStore, configured)
    return build_local_secret_store(request.app.state.settings)


def get_provider_connectivity_gateway(request: Request) -> ProviderConnectivityGateway:
    """Resolve an injected test double or the fixed internal LLM-Gateway client."""

    configured = getattr(request.app.state, "provider_connectivity_gateway", None)
    if configured is not None:
        return cast(ProviderConnectivityGateway, configured)
    return build_provider_connectivity_gateway()


def get_provider_connectivity_rate_limiter(request: Request) -> ProviderTestRateLimiter:
    """Resolve an injected limiter or the process-shared Valkey-backed limiter."""

    configured = getattr(request.app.state, "provider_test_rate_limiter", None)
    if configured is not None:
        return cast(ProviderTestRateLimiter, configured)
    return get_provider_test_rate_limiter()


SecretStore = Annotated[TenantSecretStore, Depends(get_provider_secret_store)]
ConnectivityGateway = Annotated[
    ProviderConnectivityGateway,
    Depends(get_provider_connectivity_gateway),
]
ConnectivityRateLimiter = Annotated[
    ProviderTestRateLimiter,
    Depends(get_provider_connectivity_rate_limiter),
]


@router.get("", response_model=SuccessEnvelope[list[ProviderView]])
async def list_provider_connections(
    session: DatabaseSession,
    user_id: WorkforceUserId,
    tenant_id: TenantId,
) -> SuccessEnvelope[list[ProviderView]] | JSONResponse:
    try:
        providers = await list_providers(
            session,
            user_id=user_id,
            tenant_id=tenant_id,
        )
    except ProviderForbiddenError:
        return _forbidden()
    return SuccessEnvelope(data=list(providers))


@router.post(
    "",
    response_model=SuccessEnvelope[ProviderView],
    status_code=status.HTTP_201_CREATED,
)
async def create_provider_connection(
    request: ProviderCreateRequest,
    session: DatabaseSession,
    user_id: WorkforceUserId,
    tenant_id: TenantId,
    secret_store: SecretStore,
) -> SuccessEnvelope[ProviderView] | JSONResponse:
    try:
        provider = await create_provider(
            session,
            user_id=user_id,
            tenant_id=tenant_id,
            request=request,
            secret_store=secret_store,
        )
    except ProviderForbiddenError:
        return _forbidden()
    except ProviderConflictError:
        return _conflict("PROVIDER_CONFLICT", "Provider display name already exists.")
    except ProviderSecretCleanupError:
        return _cleanup_failure()
    return SuccessEnvelope(data=provider)


@router.post(
    "/{provider_connection_id}/test",
    response_model=SuccessEnvelope[ProviderConnectivityView],
)
async def test_provider_connection(
    provider_connection_id: UUID,
    request: Request,
    session: DatabaseSession,
    user_id: WorkforceUserId,
    tenant_id: TenantId,
    secret_store: SecretStore,
    gateway: ConnectivityGateway,
    rate_limiter: ConnectivityRateLimiter,
) -> SuccessEnvelope[ProviderConnectivityView] | JSONResponse:
    # A route with no Pydantic body parameter would normally ignore JSON. Reject any
    # non-empty body explicitly so model/prompt/baseUrl fields can never be mistaken
    # for supported connectivity-test controls.
    if (await request.body()).strip():
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "Provider connectivity test does not accept a request body.",
                }
            },
        )

    try:
        result = await test_provider_connectivity(
            session,
            user_id=user_id,
            tenant_id=tenant_id,
            provider_connection_id=provider_connection_id,
            secret_store=secret_store,
            gateway=gateway,
            rate_limiter=rate_limiter,
        )
    except ProviderNotFoundError:
        return _not_found()
    except ProviderForbiddenError:
        return _forbidden()
    except ProviderTestRateLimitedError as error:
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(error.retry_after_seconds)},
            content={
                "error": {
                    "code": "PROVIDER_TEST_RATE_LIMITED",
                    "message": "Provider connectivity-test rate limit exceeded.",
                }
            },
        )
    except ProviderTestUnavailableError:
        return _test_unavailable()
    except ProviderTestStaleError:
        return _conflict(
            "PROVIDER_TEST_STALE",
            "Provider credential changed during the test. Retry the connectivity test.",
        )
    return SuccessEnvelope(data=result)


@router.get(
    "/{provider_connection_id}",
    response_model=SuccessEnvelope[ProviderView],
)
async def get_provider_by_id(
    provider_connection_id: UUID,
    session: DatabaseSession,
    user_id: WorkforceUserId,
    tenant_id: TenantId,
) -> SuccessEnvelope[ProviderView] | JSONResponse:
    try:
        provider = await get_provider(
            session,
            user_id=user_id,
            tenant_id=tenant_id,
            provider_connection_id=provider_connection_id,
        )
    except ProviderNotFoundError:
        return _not_found()
    except ProviderForbiddenError:
        return _forbidden()
    return SuccessEnvelope(data=provider)


@router.patch(
    "/{provider_connection_id}",
    response_model=SuccessEnvelope[ProviderView],
)
async def update_provider_by_id(
    provider_connection_id: UUID,
    request: ProviderUpdateRequest,
    session: DatabaseSession,
    user_id: WorkforceUserId,
    tenant_id: TenantId,
    secret_store: SecretStore,
) -> SuccessEnvelope[ProviderView] | JSONResponse:
    try:
        provider = await update_provider(
            session,
            user_id=user_id,
            tenant_id=tenant_id,
            provider_connection_id=provider_connection_id,
            request=request,
            secret_store=secret_store,
        )
    except ProviderNotFoundError:
        return _not_found()
    except ProviderForbiddenError:
        return _forbidden()
    except ProviderConflictError:
        return _conflict("PROVIDER_CONFLICT", "Provider display name already exists.")
    except ProviderSecretCleanupError:
        return _cleanup_failure()
    return SuccessEnvelope(data=provider)


@router.delete(
    "/{provider_connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_provider_by_id(
    provider_connection_id: UUID,
    session: DatabaseSession,
    user_id: WorkforceUserId,
    tenant_id: TenantId,
    secret_store: SecretStore,
) -> Response | JSONResponse:
    try:
        await delete_provider(
            session,
            user_id=user_id,
            tenant_id=tenant_id,
            provider_connection_id=provider_connection_id,
            secret_store=secret_store,
        )
    except ProviderNotFoundError:
        return _not_found()
    except ProviderForbiddenError:
        return _forbidden()
    except ProviderReferencedError:
        return _conflict(
            "PROVIDER_IN_USE",
            "Provider connection is referenced by a model configuration.",
        )
    except ProviderSecretCleanupError:
        return _cleanup_failure()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _not_found() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "PROVIDER_NOT_FOUND", "message": "Provider not found."}},
    )


def _forbidden() -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={"error": {"code": "FORBIDDEN", "message": "Permission denied."}},
    )


def _conflict(code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"error": {"code": code, "message": message}},
    )


def _cleanup_failure() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "SECRET_STORE_CLEANUP_FAILED",
                "message": "Provider secret cleanup did not complete.",
            }
        },
    )


def _test_unavailable() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "PROVIDER_TEST_UNAVAILABLE",
                "message": "Provider connectivity testing is temporarily unavailable.",
            }
        },
    )
