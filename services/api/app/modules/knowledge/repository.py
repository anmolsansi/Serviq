"""Tenant-scoped persistence operations for knowledge sources and upload cleanup."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.knowledge.models import KnowledgeSource, KnowledgeUploadCleanup

CLEANUP_STATUSES = ("prepared", "pending", "referenced", "succeeded", "exhausted")


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


def add_file_knowledge_source(
    session: AsyncSession,
    *,
    source_id: UUID,
    tenant_id: UUID,
    source_type: str,
    name: str,
    object_key: str,
    access_scope: str,
    created_by: UUID,
    now: datetime,
) -> KnowledgeSource:
    source = KnowledgeSource(
        id=source_id,
        tenant_id=tenant_id,
        source_type=source_type,
        name=name,
        source_uri=None,
        object_key=object_key,
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


def add_upload_cleanup_intent(
    session: AsyncSession,
    *,
    cleanup_id: UUID,
    tenant_id: UUID,
    source_id: UUID,
    object_id: UUID,
    object_key: str,
    next_attempt_at: datetime,
    now: datetime,
) -> KnowledgeUploadCleanup:
    cleanup = KnowledgeUploadCleanup(
        id=cleanup_id,
        tenant_id=tenant_id,
        source_id=source_id,
        object_id=object_id,
        object_key=object_key,
        status="prepared",
        attempt_count=0,
        next_attempt_at=next_attempt_at,
        last_error_code=None,
        resolved_at=None,
        created_at=now,
        updated_at=now,
    )
    session.add(cleanup)
    return cleanup


async def get_upload_cleanup(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    cleanup_id: UUID,
) -> KnowledgeUploadCleanup | None:
    result = await session.execute(
        select(KnowledgeUploadCleanup).where(
            KnowledgeUploadCleanup.tenant_id == tenant_id,
            KnowledgeUploadCleanup.id == cleanup_id,
        )
    )
    return result.scalar_one_or_none()


async def get_upload_cleanup_for_update(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    cleanup_id: UUID,
) -> KnowledgeUploadCleanup | None:
    result = await session.execute(
        select(KnowledgeUploadCleanup)
        .where(
            KnowledgeUploadCleanup.tenant_id == tenant_id,
            KnowledgeUploadCleanup.id == cleanup_id,
        )
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def list_due_upload_cleanup_ids(
    session: AsyncSession,
    *,
    now: datetime,
    limit: int = 100,
) -> tuple[tuple[UUID, UUID], ...]:
    """Return only tenant/cleanup IDs, never object keys, for trusted sweep scheduling."""

    result = await session.execute(
        select(KnowledgeUploadCleanup.tenant_id, KnowledgeUploadCleanup.id)
        .where(
            KnowledgeUploadCleanup.status.in_(("prepared", "pending")),
            KnowledgeUploadCleanup.next_attempt_at <= now,
        )
        .order_by(KnowledgeUploadCleanup.next_attempt_at, KnowledgeUploadCleanup.id)
        .limit(limit)
    )
    return tuple((row.tenant_id, row.id) for row in result)


async def count_upload_cleanups_by_status(
    session: AsyncSession,
) -> dict[str, int]:
    """Internal operator metric source that exposes counts but never object keys."""

    result = await session.execute(
        select(KnowledgeUploadCleanup.status, func.count(KnowledgeUploadCleanup.id)).group_by(
            KnowledgeUploadCleanup.status
        )
    )
    counts = {status: 0 for status in CLEANUP_STATUSES}
    for status, count in result:
        counts[str(status)] = int(count)
    return counts


def mark_upload_cleanup_pending(
    cleanup: KnowledgeUploadCleanup,
    *,
    next_attempt_at: datetime,
    error_code: str,
    now: datetime,
) -> None:
    if cleanup.status not in {"prepared", "pending"}:
        raise ValueError("Only unresolved cleanup state can be armed for retry.")
    cleanup.status = "pending"
    cleanup.next_attempt_at = next_attempt_at
    cleanup.last_error_code = error_code
    cleanup.resolved_at = None
    cleanup.updated_at = now


def mark_upload_cleanup_referenced(
    cleanup: KnowledgeUploadCleanup,
    *,
    now: datetime,
) -> None:
    if cleanup.status != "prepared":
        raise ValueError("Only a prepared cleanup can become referenced.")
    cleanup.status = "referenced"
    cleanup.next_attempt_at = None
    cleanup.last_error_code = None
    cleanup.resolved_at = now
    cleanup.updated_at = now


def mark_upload_cleanup_succeeded(
    cleanup: KnowledgeUploadCleanup,
    *,
    now: datetime,
) -> None:
    if cleanup.status == "referenced":
        raise ValueError("Referenced objects must not be marked as deleted.")
    if cleanup.status == "exhausted":
        raise ValueError("Exhausted cleanup requires an explicit operator requeue contract.")
    cleanup.status = "succeeded"
    cleanup.next_attempt_at = None
    cleanup.last_error_code = None
    cleanup.resolved_at = now
    cleanup.updated_at = now


def mark_upload_cleanup_exhausted(
    cleanup: KnowledgeUploadCleanup,
    *,
    error_code: str,
    now: datetime,
) -> None:
    if cleanup.status not in {"prepared", "pending"}:
        raise ValueError("Only unresolved cleanup state can become exhausted.")
    cleanup.status = "exhausted"
    cleanup.next_attempt_at = None
    cleanup.last_error_code = error_code
    cleanup.resolved_at = now
    cleanup.updated_at = now
