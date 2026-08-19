"""Knowledge source registration, listing, tenant isolation, and capability checks."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.knowledge.errors import KnowledgeSourceForbiddenError
from app.modules.knowledge.models import KnowledgeSource
from app.modules.knowledge.repository import add_knowledge_source, list_knowledge_sources
from app.modules.knowledge.schemas import (
    KnowledgeAccessScope,
    KnowledgeSourceCreateRequest,
    KnowledgeSourceStatus,
    KnowledgeSourceType,
    KnowledgeSourceView,
)
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
