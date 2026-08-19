"""Tenant-scoped URL and sitemap knowledge source routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api import SuccessEnvelope
from app.core.database import get_database_session
from app.core.principal import require_tenant_id, require_workforce_user_id
from app.modules.knowledge.errors import KnowledgeSourceForbiddenError
from app.modules.knowledge.schemas import KnowledgeSourceCreateRequest, KnowledgeSourceView
from app.modules.knowledge.service import create_source, list_sources

router = APIRouter(prefix="/api/v1/knowledge-sources", tags=["knowledge-sources"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
WorkforceUserId = Annotated[UUID, Depends(require_workforce_user_id)]
TenantId = Annotated[UUID, Depends(require_tenant_id)]


@router.get("", response_model=SuccessEnvelope[list[KnowledgeSourceView]])
async def get_knowledge_sources(
    session: DatabaseSession,
    user_id: WorkforceUserId,
    tenant_id: TenantId,
) -> SuccessEnvelope[list[KnowledgeSourceView]] | JSONResponse:
    try:
        sources = await list_sources(
            session,
            user_id=user_id,
            tenant_id=tenant_id,
        )
    except KnowledgeSourceForbiddenError:
        return _forbidden()
    return SuccessEnvelope(data=list(sources))


@router.post(
    "",
    response_model=SuccessEnvelope[KnowledgeSourceView],
    status_code=status.HTTP_201_CREATED,
)
async def create_knowledge_source(
    request: KnowledgeSourceCreateRequest,
    session: DatabaseSession,
    user_id: WorkforceUserId,
    tenant_id: TenantId,
) -> SuccessEnvelope[KnowledgeSourceView] | JSONResponse:
    try:
        source = await create_source(
            session,
            user_id=user_id,
            tenant_id=tenant_id,
            request=request,
        )
    except KnowledgeSourceForbiddenError:
        return _forbidden()
    return SuccessEnvelope(data=source)


def _forbidden() -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={"error": {"code": "FORBIDDEN", "message": "Permission denied."}},
    )
