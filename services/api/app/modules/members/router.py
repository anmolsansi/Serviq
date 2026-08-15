"""Protected tenant workforce member-management routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api import SuccessEnvelope
from app.core.database import get_database_session
from app.core.principal import require_workforce_user_id
from app.modules.members.errors import (
    LastActiveOwnerConflictError,
    MembershipAccessNotFoundError,
    MembershipForbiddenError,
    MembershipRoleInvalidError,
)
from app.modules.members.schemas import MemberUpdateRequest, MemberView
from app.modules.members.service import list_members, update_member

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/members",
    tags=["members"],
)
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
WorkforceUserId = Annotated[UUID, Depends(require_workforce_user_id)]


@router.get("", response_model=SuccessEnvelope[list[MemberView]])
async def get_members(
    organization_id: UUID,
    session: DatabaseSession,
    user_id: WorkforceUserId,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessEnvelope[list[MemberView]] | JSONResponse:
    try:
        members = await list_members(
            session,
            user_id=user_id,
            organization_id=organization_id,
            limit=limit,
            offset=offset,
        )
    except MembershipAccessNotFoundError:
        return _not_found_response()
    except MembershipForbiddenError:
        return _forbidden_response()
    return SuccessEnvelope(data=list(members))


@router.patch("/{membership_id}", response_model=SuccessEnvelope[MemberView])
async def patch_member(
    organization_id: UUID,
    membership_id: UUID,
    request: MemberUpdateRequest,
    session: DatabaseSession,
    user_id: WorkforceUserId,
) -> SuccessEnvelope[MemberView] | JSONResponse:
    try:
        member = await update_member(
            session,
            user_id=user_id,
            organization_id=organization_id,
            membership_id=membership_id,
            request=request,
        )
    except MembershipAccessNotFoundError:
        return _not_found_response()
    except MembershipForbiddenError:
        return _forbidden_response()
    except MembershipRoleInvalidError:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "MEMBERSHIP_ROLE_INVALID",
                    "message": "One or more requested roles are not assignable.",
                }
            },
        )
    except LastActiveOwnerConflictError:
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "LAST_ACTIVE_OWNER",
                    "message": "The organization must retain at least one active owner.",
                }
            },
        )
    return SuccessEnvelope(data=member)


def _not_found_response() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "error": {
                "code": "MEMBERSHIP_NOT_FOUND",
                "message": "Membership or organization was not found.",
            }
        },
    )


def _forbidden_response() -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={
            "error": {
                "code": "FORBIDDEN",
                "message": "You do not have permission to manage members.",
            }
        },
    )
