"""Knowledge source registration, listing, tenant isolation, and capability checks."""

from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.object_storage import ObjectStorage, knowledge_raw_key
from app.modules.knowledge.errors import KnowledgeSourceForbiddenError
from app.modules.knowledge.models import KnowledgeSource
from app.modules.knowledge.repository import (
    add_file_knowledge_source,
    add_knowledge_source,
    list_knowledge_sources,
)
from app.modules.knowledge.schemas import (
    KnowledgeAccessScope,
    KnowledgeSourceCreateRequest,
    KnowledgeSourceStatus,
    KnowledgeSourceType,
    KnowledgeSourceView,
)
from app.modules.knowledge.uploads import FileKnowledgeSourceType, validate_upload
from app.modules.tenancy.errors import TenantMembershipAccessError
from app.modules.tenancy.service import resolve_tenant_membership

KNOWLEDGE_SOURCE_MANAGE_PERMISSION = "knowledge.sources.manage"


async def list_sources(
    session: AsyncSession,
    *,
    user_id: UUID,
    tenant_id: UUID,
) -> tuple[KnowledgeSourceView, ...]:
    await _require_permission(session, user_id=user_id, tenant_id=tenant_id)
    sources = await list_knowledge_sources(session, tenant_id=tenant_id)
    return tuple(_to_view(source) for source in sources)


async def create_source(
    session: AsyncSession,
    *,
    user_id: UUID,
    tenant_id: UUID,
    request: KnowledgeSourceCreateRequest,
) -> KnowledgeSourceView:
    """Register metadata only. Crawling/fetching is deliberately not part of this flow."""

    async with session.begin():
        await _require_permission(session, user_id=user_id, tenant_id=tenant_id)
        now = datetime.now(UTC)
        source = add_knowledge_source(
            session,
            source_id=uuid4(),
            tenant_id=tenant_id,
            source_type=request.source_type,
            name=request.name,
            source_uri=request.source_uri,
            access_scope=request.access_scope,
            created_by=user_id,
            now=now,
        )
        await session.flush()
        return _to_view(source)


async def create_file_source(
    session: AsyncSession,
    *,
    storage: ObjectStorage,
    user_id: UUID,
    tenant_id: UUID,
    source_type: FileKnowledgeSourceType,
    name: str,
    access_scope: Literal["customer", "internal"],
    upload: UploadFile,
) -> KnowledgeSourceView:
    """Validate and durably register one untrusted file-backed knowledge source."""

    await _require_permission(session, user_id=user_id, tenant_id=tenant_id)
    await session.rollback()
    validated = await validate_upload(upload, source_type=source_type)

    source_id = uuid4()
    object_id = uuid4()
    key = knowledge_raw_key(tenant_id=tenant_id, source_id=source_id, object_id=object_id)
    metadata = {"original-filename": validated.original_filename}
    await run_in_threadpool(
        storage.put_object,
        key,
        upload.file,
        content_type=validated.content_type,
        metadata=metadata,
    )

    try:
        async with session.begin():
            now = datetime.now(UTC)
            source = add_file_knowledge_source(
                session,
                source_id=source_id,
                tenant_id=tenant_id,
                source_type=source_type,
                name=name,
                object_key=key.value,
                access_scope=access_scope,
                created_by=user_id,
                now=now,
            )
            await session.flush()
            view = _to_view(source)
    except Exception:
        await run_in_threadpool(storage.delete_object, key)
        raise
    return view


async def _require_permission(
    session: AsyncSession,
    *,
    user_id: UUID,
    tenant_id: UUID,
) -> None:
    try:
        membership = await resolve_tenant_membership(
            session,
            user_id=user_id,
            tenant_id=tenant_id,
        )
    except TenantMembershipAccessError:
        raise KnowledgeSourceForbiddenError from None
    if KNOWLEDGE_SOURCE_MANAGE_PERMISSION not in membership.permissions:
        raise KnowledgeSourceForbiddenError


def _to_view(source: KnowledgeSource) -> KnowledgeSourceView:
    return KnowledgeSourceView(
        id=source.id,
        sourceType=cast(KnowledgeSourceType, source.source_type),
        name=source.name,
        sourceUri=source.source_uri,
        accessScope=cast(KnowledgeAccessScope, source.access_scope),
        status=cast(KnowledgeSourceStatus, source.status),
        syncVersion=source.sync_version,
        lastSyncedAt=source.last_synced_at,
        lastErrorCode=source.last_error_code,
        createdAt=source.created_at,
        updatedAt=source.updated_at,
    )
