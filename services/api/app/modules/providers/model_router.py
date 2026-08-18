"""Tenant-scoped stable model-configuration routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api import SuccessEnvelope
from app.core.database import get_database_session
from app.core.principal import require_tenant_id, require_workforce_user_id
from app.modules.providers.errors import (
    ModelConfigurationAliasConflictError,
    ModelConfigurationNotFoundError,
    ModelConfigurationProviderIneligibleError,
    ModelConfigurationReferencedError,
    ProviderForbiddenError,
    ProviderNotFoundError,
)
from app.modules.providers.schemas import (
    ModelConfigurationCreateRequest,
    ModelConfigurationUpdateRequest,
    ModelConfigurationView,
)
from app.modules.providers.service import create_model, delete_model, list_models, update_model

router = APIRouter(prefix="/api/v1/models", tags=["models"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
WorkforceUserId = Annotated[UUID, Depends(require_workforce_user_id)]
TenantId = Annotated[UUID, Depends(require_tenant_id)]


@router.get("", response_model=SuccessEnvelope[list[ModelConfigurationView]])
async def list_model_configurations(
    session: DatabaseSession,
    user_id: WorkforceUserId,
    tenant_id: TenantId,
) -> SuccessEnvelope[list[ModelConfigurationView]] | JSONResponse:
    try:
        models = await list_models(
            session,
            user_id=user_id,
            tenant_id=tenant_id,
        )
    except ProviderNotFoundError:
        return _not_found()
    except ProviderForbiddenError:
        return _forbidden()
    return SuccessEnvelope(data=list(models))


@router.post(
    "",
    response_model=SuccessEnvelope[ModelConfigurationView],
    status_code=status.HTTP_201_CREATED,
)
async def create_model_configuration(
    request: ModelConfigurationCreateRequest,
    session: DatabaseSession,
    user_id: WorkforceUserId,
    tenant_id: TenantId,
) -> SuccessEnvelope[ModelConfigurationView] | JSONResponse:
    try:
        model = await create_model(
            session,
            user_id=user_id,
            tenant_id=tenant_id,
            request=request,
        )
    except ProviderNotFoundError:
        return _provider_not_found()
    except ProviderForbiddenError:
        return _forbidden()
    except ModelConfigurationProviderIneligibleError:
        return _conflict(
            "MODEL_PROVIDER_INELIGIBLE",
            "Model configuration requires an active provider connection.",
        )
    except ModelConfigurationAliasConflictError:
        return _conflict(
            "MODEL_ALIAS_CONFLICT",
            "Model alias already exists for this tenant.",
        )
    return SuccessEnvelope(data=model)


@router.patch(
    "/{model_configuration_id}",
    response_model=SuccessEnvelope[ModelConfigurationView],
)
async def update_model_configuration(
    model_configuration_id: UUID,
    request: ModelConfigurationUpdateRequest,
    session: DatabaseSession,
    user_id: WorkforceUserId,
    tenant_id: TenantId,
) -> SuccessEnvelope[ModelConfigurationView] | JSONResponse:
    try:
        model = await update_model(
            session,
            user_id=user_id,
            tenant_id=tenant_id,
            model_configuration_id=model_configuration_id,
            request=request,
        )
    except ModelConfigurationNotFoundError:
        return _model_not_found()
    except ProviderNotFoundError:
        return _provider_not_found()
    except ProviderForbiddenError:
        return _forbidden()
    except ModelConfigurationProviderIneligibleError:
        return _conflict(
            "MODEL_PROVIDER_INELIGIBLE",
            "Model configuration requires an active provider connection.",
        )
    return SuccessEnvelope(data=model)


@router.delete(
    "/{model_configuration_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_model_configuration(
    model_configuration_id: UUID,
    session: DatabaseSession,
    user_id: WorkforceUserId,
    tenant_id: TenantId,
) -> Response | JSONResponse:
    try:
        await delete_model(
            session,
            user_id=user_id,
            tenant_id=tenant_id,
            model_configuration_id=model_configuration_id,
        )
    except ModelConfigurationNotFoundError:
        return _model_not_found()
    except ProviderNotFoundError:
        return _not_found()
    except ProviderForbiddenError:
        return _forbidden()
    except ModelConfigurationReferencedError:
        return _conflict(
            "MODEL_CONFIGURATION_IN_USE",
            "Model configuration is referenced by production configuration.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _model_not_found() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "error": {
                "code": "MODEL_CONFIGURATION_NOT_FOUND",
                "message": "Model configuration not found.",
            }
        },
    )


def _provider_not_found() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "PROVIDER_NOT_FOUND", "message": "Provider not found."}},
    )


def _not_found() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "NOT_FOUND", "message": "Resource not found."}},
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
