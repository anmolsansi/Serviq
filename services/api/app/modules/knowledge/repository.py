"""Tenant-scoped persistence for knowledge sources, cleanup, and upload quota state."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.knowledge.models import (
    KnowledgeSource,
    KnowledgeUploadCleanup,
    KnowledgeUploadReservation,
)

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
        object_size_bytes=None,
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
    object_size_bytes: int,
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
        object_size_bytes=object_size_bytes,
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


async def lock_tenant_for_knowledge_quota(
    session: AsyncSession,
    *,
    tenant_id: UUID,
) -> None:
    """Serialize tenant quota decisions without importing another domain repository."""

    result = await session.execute(
        text("SELECT id FROM tenants WHERE id=:tenant_id FOR UPDATE"),
        {"tenant_id": tenant_id},
    )
    if result.scalar_one_or_none() is None:
        raise RuntimeError("Tenant disappeared during knowledge quota decision.")


async def delete_expired_unlinked_upload_reservations(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    now: datetime,
) -> int:
    result = await session.execute(
        delete(KnowledgeUploadReservation).where(
            KnowledgeUploadReservation.tenant_id == tenant_id,
            KnowledgeUploadReservation.cleanup_id.is_(None),
            KnowledgeUploadReservation.lease_expires_at <= now,
        )
    )
    return int(result.rowcount or 0)


async def get_knowledge_quota_usage(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    now: datetime,
) -> tuple[int, int, int, int, int, datetime | None]:
    """Return committed count/bytes, held count/bytes, active count, earliest lease."""

    committed = (
        await session.execute(
            select(
                func.count(KnowledgeSource.id),
                func.coalesce(func.sum(KnowledgeSource.object_size_bytes), 0),
            ).where(KnowledgeSource.tenant_id == tenant_id)
        )
    ).one()

    held_predicate = or_(
        KnowledgeUploadReservation.cleanup_id.is_not(None),
        KnowledgeUploadReservation.lease_expires_at > now,
    )
    held = (
        await session.execute(
            select(
                func.count(KnowledgeUploadReservation.id),
                func.coalesce(func.sum(KnowledgeUploadReservation.reserved_bytes), 0),
            ).where(
                KnowledgeUploadReservation.tenant_id == tenant_id,
                held_predicate,
            )
        )
    ).one()

    active = (
        await session.execute(
            select(
                func.count(KnowledgeUploadReservation.id),
                func.min(KnowledgeUploadReservation.lease_expires_at),
            ).where(
                KnowledgeUploadReservation.tenant_id == tenant_id,
                KnowledgeUploadReservation.lease_expires_at > now,
            )
        )
    ).one()

    return (
        int(committed[0]),
        int(committed[1]),
        int(held[0]),
        int(held[1]),
        int(active[0]),
        active[1],
    )


async def list_unknown_file_source_sizes(
    session: AsyncSession,
    *,
    tenant_id: UUID,
) -> tuple[tuple[UUID, str], ...]:
    result = await session.execute(
        select(KnowledgeSource.id, KnowledgeSource.object_key).where(
            KnowledgeSource.tenant_id == tenant_id,
            KnowledgeSource.object_key.is_not(None),
            KnowledgeSource.object_size_bytes.is_(None),
        )
    )
    rows: list[tuple[UUID, str]] = []
    for source_id, object_key in result:
        if not isinstance(object_key, str):
            raise RuntimeError("File-backed knowledge source has no object key.")
        rows.append((source_id, object_key))
    return tuple(rows)


async def set_file_source_size_if_unknown(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    source_id: UUID,
    object_key: str,
    object_size_bytes: int,
) -> None:
    result = await session.execute(
        update(KnowledgeSource)
        .where(
            KnowledgeSource.tenant_id == tenant_id,
            KnowledgeSource.id == source_id,
            KnowledgeSource.object_key == object_key,
            KnowledgeSource.object_size_bytes.is_(None),
        )
        .values(object_size_bytes=object_size_bytes)
    )
    if result.rowcount not in {0, 1}:
        raise RuntimeError("Knowledge source size reconciliation updated multiple rows.")


def add_upload_reservation(
    session: AsyncSession,
    *,
    reservation_id: UUID,
    tenant_id: UUID,
    source_id: UUID,
    reserved_bytes: int,
    lease_expires_at: datetime,
    now: datetime,
) -> KnowledgeUploadReservation:
    reservation = KnowledgeUploadReservation(
        id=reservation_id,
        tenant_id=tenant_id,
        source_id=source_id,
        reserved_bytes=reserved_bytes,
        cleanup_id=None,
        lease_expires_at=lease_expires_at,
        created_at=now,
        updated_at=now,
    )
    session.add(reservation)
    return reservation


async def bind_upload_reservation_to_cleanup(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    reservation_id: UUID,
    cleanup_id: UUID,
    now: datetime,
) -> None:
    result = await session.execute(
        update(KnowledgeUploadReservation)
        .where(
            KnowledgeUploadReservation.tenant_id == tenant_id,
            KnowledgeUploadReservation.id == reservation_id,
            KnowledgeUploadReservation.cleanup_id.is_(None),
        )
        .values(cleanup_id=cleanup_id, updated_at=now)
    )
    if result.rowcount != 1:
        raise RuntimeError("Knowledge upload reservation could not be bound to cleanup.")


async def expire_upload_concurrency_lease_for_cleanup(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    cleanup_id: UUID,
    now: datetime,
) -> None:
    """End request concurrency while preserving the linked byte/source quota hold."""

    await session.execute(
        update(KnowledgeUploadReservation)
        .where(
            KnowledgeUploadReservation.tenant_id == tenant_id,
            KnowledgeUploadReservation.cleanup_id == cleanup_id,
            KnowledgeUploadReservation.lease_expires_at > now,
        )
        .values(lease_expires_at=now, updated_at=now)
    )


async def release_upload_reservation(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    reservation_id: UUID,
) -> None:
    await session.execute(
        delete(KnowledgeUploadReservation).where(
            KnowledgeUploadReservation.tenant_id == tenant_id,
            KnowledgeUploadReservation.id == reservation_id,
        )
    )


async def release_upload_reservation_for_cleanup(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    cleanup_id: UUID,
) -> None:
    await session.execute(
        delete(KnowledgeUploadReservation).where(
            KnowledgeUploadReservation.tenant_id == tenant_id,
            KnowledgeUploadReservation.cleanup_id == cleanup_id,
        )
    )


async def count_upload_reservations(
    session: AsyncSession,
    *,
    tenant_id: UUID | None = None,
) -> int:
    statement = select(func.count(KnowledgeUploadReservation.id))
    if tenant_id is not None:
        statement = statement.where(KnowledgeUploadReservation.tenant_id == tenant_id)
    return int((await session.execute(statement)).scalar_one())


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
