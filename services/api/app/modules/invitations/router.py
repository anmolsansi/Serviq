"""Protected organization invitation management routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api import SuccessEnvelope
from app.core.config import load_settings
from app.core.database import get_database_session
from app.core.principal import require_workforce_user_id
from app.modules.invitations.errors import (
    InvitationAccessNotFoundError,
    InvitationConflictError,
    InvitationForbiddenError,
    InvitationLifecycleConflictError,
    InvitationRoleInvalidError,
)
from app.modules.invitations.schemas import (
    InvitationCreateRequest,
    InvitationCreateView,
    InvitationView,
)
from app.modules.invitations.service import (
    create_invitation,
    list_invitations,
    revoke_invitation,
)

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/invitations",
    tags=["invitations"],
)
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
WorkforceUserId = Annotated[UUID, Depends(require_workforce_user_id)]


@router.get("", response_model=SuccessEnvelope[list[InvitationView]])
async def get_invitations(
    organization_id: UUID,
    session: DatabaseSession,
    user_id: WorkforceUserId,
) -> SuccessEnvelope[list[InvitationView]] | JSONResponse:
    try:
        invitations = await list_invitations(
            session,
            user_id=user_id,
            organization_id=organization_id,
        )
    except InvitationAccessNotFoundError:
        return _not_found_response()
    except InvitationForbiddenError:
        return _forbidden_response()
    return SuccessEnvelope(data=list(invitations))


@router.post(
    "",
    response_model=SuccessEnvelope[InvitationCreateView],
    status_code=status.HTTP_201_CREATED,
)
async def post_invitation(
    organization_id: UUID,
    request: InvitationCreateRequest,
    session: DatabaseSession,
    user_id: WorkforceUserId,
) -> SuccessEnvelope[InvitationCreateView] | JSONResponse:
    settings = load_settings()
    try:
        invitation = await create_invitation(
            session,
            user_id=user_id,
            organization_id=organization_id,
            request=request,
            public_base_url=str(settings.serviq_public_base_url),
        )
    except InvitationAccessNotFoundError:
        return _not_found_response()
    except InvitationForbiddenError:
        return _forbidden_response()
    except InvitationRoleInvalidError:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "INVITATION_ROLE_INVALID",
                    "message": "One or more requested roles are not assignable.",
                }
            },
        )
    except InvitationConflictError:
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "INVITATION_CONFLICT",
                    "message": "A pending invitation already exists for this email.",
                }
            },
        )
    return SuccessEnvelope(data=invitation)


@router.delete(
    "/{invitation_id}",
    response_model=SuccessEnvelope[InvitationView],
)
async def delete_invitation(
    organization_id: UUID,
    invitation_id: UUID,
    session: DatabaseSession,
    user_id: WorkforceUserId,
) -> SuccessEnvelope[InvitationView] | JSONResponse:
    try:
        invitation = await revoke_invitation(
            session,
            user_id=user_id,
            organization_id=organization_id,
            invitation_id=invitation_id,
        )
    except InvitationAccessNotFoundError:
        return _not_found_response()
    except InvitationForbiddenError:
        return _forbidden_response()
    except InvitationLifecycleConflictError:
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "INVITATION_LIFECYCLE_CONFLICT",
                    "message": "Invitation cannot be revoked from its current state.",
                }
            },
        )
    return SuccessEnvelope(data=invitation)


def _not_found_response() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "error": {
                "code": "INVITATION_NOT_FOUND",
                "message": "Invitation or organization was not found.",
            }
        },
    )


def _forbidden_response() -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={
            "error": {
                "code": "FORBIDDEN",
                "message": "You do not have permission to manage invitations.",
            }
        },
    )
