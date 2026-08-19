"""Tenant-scoped URL, sitemap, and file knowledge source routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from app.core.api import SuccessEnvelope
from app.core.database import get_database_session
from app.core.object_storage import ObjectStorageError
from app.core.principal import require_tenant_id, require_workforce_user_id
from app.modules.knowledge.errors import KnowledgeSourceForbiddenError
from app.modules.knowledge.schemas import KnowledgeSourceCreateRequest, KnowledgeSourceView
from app.modules.knowledge.service import create_file_source, create_source, list_sources
from app.modules.knowledge.storage import get_knowledge_object_storage
from app.modules.knowledge.uploads import (
    KnowledgeUploadTooLargeError,
    KnowledgeUploadValidationError,
    parse_file_source_type,
    validate_access_scope,
    validate_name,
)

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
        sources = await list_sources(session, user_id=user_id, tenant_id=tenant_id)
    except KnowledgeSourceForbiddenError:
        return _forbidden()
    return SuccessEnvelope(data=list(sources))


@router.post(
    "",
    response_model=SuccessEnvelope[KnowledgeSourceView],
    status_code=status.HTTP_201_CREATED,
)
async def create_knowledge_source(
    http_request: Request,
    session: DatabaseSession,
    user_id: WorkforceUserId,
    tenant_id: TenantId,
) -> SuccessEnvelope[KnowledgeSourceView] | JSONResponse:
    content_type = http_request.headers.get("content-type", "").lower()
    if content_type.startswith("multipart/form-data"):
        return await _create_file_knowledge_source(
            http_request,
            session=session,
            user_id=user_id,
            tenant_id=tenant_id,
        )
    if not content_type.startswith("application/json"):
        return _error(415, "UNSUPPORTED_MEDIA_TYPE", "Use JSON or multipart/form-data.")

    try:
        request = KnowledgeSourceCreateRequest.model_validate(await http_request.json())
    except (ValidationError, ValueError, TypeError):
        return _error(422, "VALIDATION_ERROR", "Knowledge source request is invalid.")

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


async def _create_file_knowledge_source(
    request: Request,
    *,
    session: AsyncSession,
    user_id: UUID,
    tenant_id: UUID,
) -> SuccessEnvelope[KnowledgeSourceView] | JSONResponse:
    try:
        form = await request.form(max_files=1, max_fields=3, max_part_size=25 * 1024 * 1024)
        allowed = {"sourceType", "name", "accessScope", "file"}
        has_invalid_fields = set(form.keys()) != allowed or any(
            len(form.getlist(key)) != 1 for key in allowed
        )
        if has_invalid_fields:
            raise KnowledgeUploadValidationError("Multipart fields are invalid.")

        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise KnowledgeUploadValidationError("Exactly one file upload is required.")
        source_type = parse_file_source_type(form.get("sourceType"))
        name = validate_name(form.get("name"))
        access_scope = validate_access_scope(form.get("accessScope"))

        source = await create_file_source(
            session,
            storage=get_knowledge_object_storage(),
            user_id=user_id,
            tenant_id=tenant_id,
            source_type=source_type,
            name=name,
            access_scope=access_scope,
            upload=upload,
        )
    except KnowledgeSourceForbiddenError:
        return _forbidden()
    except KnowledgeUploadTooLargeError:
        return _error(413, "UPLOAD_TOO_LARGE", "Uploaded knowledge file exceeds the V1 limit.")
    except KnowledgeUploadValidationError:
        return _error(422, "VALIDATION_ERROR", "Knowledge file upload is invalid.")
    except ObjectStorageError:
        return _error(
            503,
            "OBJECT_STORAGE_UNAVAILABLE",
            "Knowledge file storage is unavailable.",
        )
    return SuccessEnvelope(data=source)


def _forbidden() -> JSONResponse:
    return _error(403, "FORBIDDEN", "Permission denied.")


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )
