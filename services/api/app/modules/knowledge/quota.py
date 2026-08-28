"""Authoritative tenant quota reservation and legacy byte reconciliation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.object_storage import (
    KnowledgeRawObjectKey,
    ObjectStorage,
    ObjectStorageError,
    knowledge_raw_key,
)
from app.modules.knowledge.errors import (
    KnowledgeQuotaUnavailableError,
    KnowledgeSourceQuotaExceededError,
    KnowledgeStorageQuotaExceededError,
    KnowledgeUploadConcurrencyLimitedError,
)
from app.modules.knowledge.repository import (
    add_upload_reservation,
    delete_expired_unlinked_upload_reservations,
    get_knowledge_quota_usage,
    list_unknown_file_source_sizes,
    lock_tenant_for_knowledge_quota,
    release_upload_reservation,
    set_file_source_size_if_unknown,
)

logger = logging.getLogger(__name__)

KNOWLEDGE_SOURCE_LIMIT = 100
KNOWLEDGE_STORED_BYTE_LIMIT = 1024 * 1024 * 1024
KNOWLEDGE_CONCURRENT_UPLOAD_LIMIT = 3
KNOWLEDGE_UPLOAD_LEASE = timedelta(minutes=10)
MAX_KNOWLEDGE_FILE_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class KnowledgeQuotaUsage:
    committed_sources: int
    committed_bytes: int
    held_sources: int
    held_bytes: int
    active_uploads: int
    earliest_active_lease: datetime | None

    @property
    def charged_sources(self) -> int:
        return self.committed_sources + self.held_sources

    @property
    def charged_bytes(self) -> int:
        return self.committed_bytes + self.held_bytes


@dataclass(frozen=True, slots=True)
class KnowledgeUploadReservationClaim:
    reservation_id: UUID
    source_id: UUID
    reserved_bytes: int
    lease_expires_at: datetime


def _safe_log(event: str, *, tenant_id: UUID, outcome: str, **extra: int | str) -> None:
    logger.info(
        event,
        extra={
            "tenant_id": str(tenant_id),
            "quota_outcome": outcome,
            **extra,
        },
    )


def _usage_from_row(
    row: tuple[int, int, int, int, int, datetime | None],
) -> KnowledgeQuotaUsage:
    return KnowledgeQuotaUsage(
        committed_sources=row[0],
        committed_bytes=row[1],
        held_sources=row[2],
        held_bytes=row[3],
        active_uploads=row[4],
        earliest_active_lease=row[5],
    )


async def reconcile_legacy_file_sizes(
    session: AsyncSession,
    *,
    storage: ObjectStorage,
    tenant_id: UUID,
) -> int:
    """Measure legacy file rows without holding a DB transaction over storage HEAD."""

    async with session.begin():
        unknown = await list_unknown_file_source_sizes(session, tenant_id=tenant_id)

    if not unknown:
        return 0

    measured: list[tuple[UUID, str, int]] = []
    for source_id, object_key in unknown:
        try:
            key = parse_knowledge_raw_object_key(
                object_key,
                tenant_id=tenant_id,
                source_id=source_id,
            )
            metadata = await run_in_threadpool(storage.head, key)
        except (ObjectStorageError, ValueError, TypeError):
            _safe_log(
                "knowledge_quota_legacy_reconciliation_failed",
                tenant_id=tenant_id,
                outcome="unavailable",
            )
            raise KnowledgeQuotaUnavailableError from None

        content_length = metadata.content_length
        if not 0 <= content_length <= MAX_KNOWLEDGE_FILE_BYTES:
            _safe_log(
                "knowledge_quota_legacy_reconciliation_failed",
                tenant_id=tenant_id,
                outcome="invalid_size",
            )
            raise KnowledgeQuotaUnavailableError
        measured.append((source_id, object_key, content_length))

    async with session.begin():
        await lock_tenant_for_knowledge_quota(session, tenant_id=tenant_id)
        for source_id, object_key, content_length in measured:
            await set_file_source_size_if_unknown(
                session,
                tenant_id=tenant_id,
                source_id=source_id,
                object_key=object_key,
                object_size_bytes=content_length,
            )
        await session.flush()

    _safe_log(
        "knowledge_quota_legacy_reconciled",
        tenant_id=tenant_id,
        outcome="reconciled",
        reconciled_sources=len(measured),
    )
    return len(measured)


def parse_knowledge_raw_object_key(
    value: str,
    *,
    tenant_id: UUID,
    source_id: UUID,
) -> KnowledgeRawObjectKey:
    """Rebuild only the approved generated raw key; never accept arbitrary object paths."""

    parts = value.split("/")
    if len(parts) != 6 or parts[0] != "tenants" or parts[2] != "knowledge" or parts[4] != "raw":
        raise ValueError("Knowledge object key does not match the generated raw-key contract.")
    parsed_tenant = UUID(parts[1])
    parsed_source = UUID(parts[3])
    parsed_object = UUID(parts[5])
    if parsed_tenant != tenant_id or parsed_source != source_id:
        raise ValueError("Knowledge object key identity does not match trusted tenant/source.")
    key = knowledge_raw_key(
        tenant_id=parsed_tenant,
        source_id=parsed_source,
        object_id=parsed_object,
    )
    if key.value != value:
        raise ValueError("Knowledge object key is not canonical.")
    return key


async def assert_source_capacity(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    now: datetime,
) -> KnowledgeQuotaUsage:
    """Lock tenant quota state and ensure one more source row can be created."""

    await lock_tenant_for_knowledge_quota(session, tenant_id=tenant_id)
    reclaimed = await delete_expired_unlinked_upload_reservations(
        session,
        tenant_id=tenant_id,
        now=now,
    )
    usage = _usage_from_row(
        await get_knowledge_quota_usage(session, tenant_id=tenant_id, now=now)
    )
    if usage.charged_sources >= KNOWLEDGE_SOURCE_LIMIT:
        _safe_log(
            "knowledge_quota_rejected",
            tenant_id=tenant_id,
            outcome="source_limit",
            charged_sources=usage.charged_sources,
            source_limit=KNOWLEDGE_SOURCE_LIMIT,
        )
        raise KnowledgeSourceQuotaExceededError
    if reclaimed:
        _safe_log(
            "knowledge_quota_reservations_reclaimed",
            tenant_id=tenant_id,
            outcome="reclaimed",
            reclaimed_reservations=reclaimed,
        )
    return usage


async def reserve_file_upload(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    source_id: UUID,
    reserved_bytes: int,
    now: datetime | None = None,
) -> KnowledgeUploadReservationClaim:
    """Atomically reserve source, byte, and concurrency capacity for one validated upload."""

    if not 0 <= reserved_bytes <= MAX_KNOWLEDGE_FILE_BYTES:
        raise ValueError("Reserved upload bytes are outside the approved file-size boundary.")

    current = now or datetime.now(UTC)
    reservation_id = uuid4()
    lease_expires_at = current + KNOWLEDGE_UPLOAD_LEASE

    async with session.begin():
        await lock_tenant_for_knowledge_quota(session, tenant_id=tenant_id)
        reclaimed = await delete_expired_unlinked_upload_reservations(
            session,
            tenant_id=tenant_id,
            now=current,
        )
        unknown = await list_unknown_file_source_sizes(session, tenant_id=tenant_id)
        if unknown:
            raise KnowledgeQuotaUnavailableError

        usage = _usage_from_row(
            await get_knowledge_quota_usage(session, tenant_id=tenant_id, now=current)
        )
        if usage.charged_sources >= KNOWLEDGE_SOURCE_LIMIT:
            _safe_log(
                "knowledge_quota_rejected",
                tenant_id=tenant_id,
                outcome="source_limit",
                charged_sources=usage.charged_sources,
                source_limit=KNOWLEDGE_SOURCE_LIMIT,
            )
            raise KnowledgeSourceQuotaExceededError
        if usage.charged_bytes + reserved_bytes > KNOWLEDGE_STORED_BYTE_LIMIT:
            _safe_log(
                "knowledge_quota_rejected",
                tenant_id=tenant_id,
                outcome="byte_limit",
                charged_bytes=usage.charged_bytes,
                requested_bytes=reserved_bytes,
                byte_limit=KNOWLEDGE_STORED_BYTE_LIMIT,
            )
            raise KnowledgeStorageQuotaExceededError
        if usage.active_uploads >= KNOWLEDGE_CONCURRENT_UPLOAD_LIMIT:
            earliest = usage.earliest_active_lease
            retry_after = 1
            if earliest is not None:
                retry_after = max(ceil((earliest - current).total_seconds()), 1)
            _safe_log(
                "knowledge_quota_rejected",
                tenant_id=tenant_id,
                outcome="concurrency_limit",
                active_uploads=usage.active_uploads,
                concurrency_limit=KNOWLEDGE_CONCURRENT_UPLOAD_LIMIT,
                retry_after_seconds=retry_after,
            )
            raise KnowledgeUploadConcurrencyLimitedError(retry_after)

        add_upload_reservation(
            session,
            reservation_id=reservation_id,
            tenant_id=tenant_id,
            source_id=source_id,
            reserved_bytes=reserved_bytes,
            lease_expires_at=lease_expires_at,
            now=current,
        )
        await session.flush()

    _safe_log(
        "knowledge_quota_reserved",
        tenant_id=tenant_id,
        outcome="reserved",
        reservation_id=str(reservation_id),
        reserved_bytes=reserved_bytes,
        lease_seconds=int(KNOWLEDGE_UPLOAD_LEASE.total_seconds()),
        reclaimed_reservations=reclaimed,
    )
    return KnowledgeUploadReservationClaim(
        reservation_id=reservation_id,
        source_id=source_id,
        reserved_bytes=reserved_bytes,
        lease_expires_at=lease_expires_at,
    )


async def release_unlinked_reservation(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    reservation_id: UUID,
) -> None:
    """Release a pre-PUT reservation only when cleanup binding never committed."""

    async with session.begin():
        await release_upload_reservation(
            session,
            tenant_id=tenant_id,
            reservation_id=reservation_id,
        )
        await session.flush()
    _safe_log(
        "knowledge_quota_reservation_released",
        tenant_id=tenant_id,
        outcome="unlinked_released",
        reservation_id=str(reservation_id),
    )
