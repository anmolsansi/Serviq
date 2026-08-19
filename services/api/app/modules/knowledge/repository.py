"""Tenant-scoped persistence operations for knowledge source metadata."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.knowledge.models import KnowledgeSource


async def list_knowledge_sources(
    session: AsyncSession,
    *,
    tenant_id: UUID,
) -> tuple[KnowledgeSource, ...]:
    result = await session.execute(
        select(KnowledgeSource)
        .where(KnowledgeSource.tenant_id == tenant_id)
        .order_by(KnowledgeSource.created_at, KnowledgeSource.id)
    )
    return tuple(result.scalars().all())


def add_knowledge_source(
    session: AsyncSession,
    *,
    source_id: UUID,
    tenant_id: UUID,
    source_type: str,
    name: str,
    source_uri: str,
    access_scope: str,
    created_by: UUID,
    now: datetime,
) -> KnowledgeSource:
    source = KnowledgeSource(
        id=source_id,
        tenant_id=tenant_id,
        source_type=source_type,
        name=name,
        source_uri=source_uri,
        object_key=None,
        access_scope=access_scope,
        status="pending",
        sync_version=0,
        last_synced_at=None,
        last_error_code=None,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    session.add(source)
    return source
