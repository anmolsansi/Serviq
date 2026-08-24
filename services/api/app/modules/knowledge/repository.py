"""Tenant-scoped persistence operations for knowledge source metadata."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.knowledge.models import KnowledgeSource, KnowledgeUploadCleanup


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


def add_knowledge_upload_cleanup(
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
    """Create the pre-PUT durable cleanup intent frozen by ADR-018/CCR-006."""

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


async def get_knowledge_upload_cleanup_for_update(
    session: AsyncSession,
    *,
    cleanup_id: UUID,
    tenant_id: UUID,
) -> KnowledgeUploadCleanup | None:
    """Lock one tenant-owned cleanup row without exposing foreign-tenant state."""

    result = await session.execute(
        select(KnowledgeUploadCleanup)
        .where(
            KnowledgeUploadCleanup.id == cleanup_id,
            KnowledgeUploadCleanup.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    return result.scalar_one_or_none()


def mark_knowledge_upload_cleanup_referenced(
    cleanup: KnowledgeUploadCleanup,
    *,
    now: datetime,
) -> None:
    cleanup.status = "referenced"
    cleanup.next_attempt_at = None
    cleanup.last_error_code = None
    cleanup.resolved_at = now
    cleanup.updated_at = now


def arm_knowledge_upload_cleanup(
    cleanup: KnowledgeUploadCleanup,
    *,
    next_attempt_at: datetime,
    error_code: str,
    now: datetime,
) -> bool:
    """Move prepared/pending work to the bounded retry queue idempotently."""

    if cleanup.status not in {"prepared", "pending"}:
        return False
    cleanup.status = "pending"
    cleanup.next_attempt_at = next_attempt_at
    cleanup.last_error_code = error_code
    cleanup.resolved_at = None
    cleanup.updated_at = now
    return True


def mark_knowledge_upload_cleanup_succeeded(
    cleanup: KnowledgeUploadCleanup,
    *,
    now: datetime,
) -> bool:
    if cleanup.status not in {"prepared", "pending"}:
        return False
    cleanup.status = "succeeded"
    cleanup.next_attempt_at = None
    cleanup.last_error_code = None
    cleanup.resolved_at = now
    cleanup.updated_at = now
    return True


def mark_knowledge_upload_cleanup_exhausted(
    cleanup: KnowledgeUploadCleanup,
    *,
    error_code: str,
    now: datetime,
) -> None:
    cleanup.status = "exhausted"
    cleanup.next_attempt_at = None
    cleanup.last_error_code = error_code
    cleanup.resolved_at = now
    cleanup.updated_at = now


async def knowledge_upload_cleanup_status_counts(
    session: AsyncSession,
) -> dict[str, int]:
    """Return operator-safe durable counts without object keys or document content."""

    result = await session.execute(
        select(KnowledgeUploadCleanup.status, func.count(KnowledgeUploadCleanup.id)).group_by(
            KnowledgeUploadCleanup.status
        )
    )
    return {status: int(count) for status, count in result.all()}
