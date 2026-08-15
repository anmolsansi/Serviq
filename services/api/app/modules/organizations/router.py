"""Workforce organization list and creation routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api import SuccessEnvelope
from app.core.database import get_database_session
from app.core.principal import require_workforce_user_id
from app.modules.organizations.errors import (
    OrganizationSlugConflictError,
    OwnerRoleUnavailableError,
)
from app.modules.organizations.schemas import OrganizationCreateRequest, OrganizationView
from app.modules.organizations.service import create_organization, list_organizations

router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
WorkforceUserId = Annotated[UUID, Depends(require_workforce_user_id)]


@router.get("", response_model=SuccessEnvelope[list[OrganizationView]])
async def get_organizations(
    session: DatabaseSession,
    user_id: WorkforceUserId,
) -> SuccessEnvelope[list[OrganizationView]]:
    organizations = await list_organizations(session, user_id=user_id)
    return SuccessEnvelope(data=list(organizations))


@router.post(
    "",
    response_model=SuccessEnvelope[OrganizationView],
    status_code=status.HTTP_201_CREATED,
)
async def post_organization(
    request: OrganizationCreateRequest,
    session: DatabaseSession,
    user_id: WorkforceUserId,
) -> SuccessEnvelope[OrganizationView] | JSONResponse:
    try:
        organization = await create_organization(
            session,
            user_id=user_id,
            request=request,
        )
    except OrganizationSlugConflictError:
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "ORGANIZATION_SLUG_CONFLICT",
                    "message": "Organization slug is already in use.",
                }
            },
        )
    except OwnerRoleUnavailableError:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "ORGANIZATION_BOOTSTRAP_ERROR",
                    "message": "Organization could not be created.",
                }
            },
        )
    return SuccessEnvelope(data=organization)
