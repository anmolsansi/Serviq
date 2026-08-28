"""Durable, tenant-safe reconciliation for failed raw knowledge uploads."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.object_storage import ObjectStorage, ObjectStorageError, knowledge_raw_key
from app.modules.knowledge.repository import (
    get_upload_cleanup_for_update,
    list_due_upload_cleanup_ids,
    mark_upload_cleanup_exhausted,
    mark_upload_cleanup_pending,
    mark_upload_cleanup_succeeded,
    release_upload_reservation_for_cleanup,
)

logger = logging.getLogger(__name__)

PREPARED_STALE_AFTER = timedelta(minutes=15)
FIRST_RETRY_DELAY = timedelta(seconds=30)
SECOND_RETRY_DELAY = timedelta(minutes=5)
THIRD_RETRY_DELAY = timedelta(minutes=30)
MAX_RECONCILIATION_ATTEMPTS = 3
OBJECT_STORAGE_ERROR_CODE = "OBJECT_STORAGE_UNAVAILABLE"
PUT_OUTCOME_AMBIGUOUS_ERROR_CODE = "OBJECT_STORAGE_PUT_OUTCOME_AMBIGUOUS"
SOURCE_PERSISTENCE_ERROR_CODE = "KNOWLEDGE_SOURCE_PERSISTENCE_FAILED"
KEY_MISMATCH_ERROR_CODE = "KNOWLEDGE_UPLOAD_CLEANUP_KEY_MISMATCH"

CleanupReplayOutcome = Literal[
    "not_due",
    "noop_referenced",
    "noop_succeeded",
    "exhausted",
    "succeeded",
    "retry_scheduled",
]


class KnowledgeUploadCleanupUnavailableError(RuntimeError):
    """Safe tenant-scoped result for a missing or foreign cleanup obligation."""

    def __init__(self) -> None:
        super().__init__("Knowledge upload cleanup is unavailable.")


@dataclass(frozen=True, slots=True)
class CleanupReplayResult:
    cleanup_id: UUID
    tenant_id: UUID
    outcome: CleanupReplayOutcome
    attempt_count: int


@dataclass(frozen=True, slots=True)
class _CleanupClaim:
    cleanup_id: UUID
    tenant_id: UUID
    source_id: UUID
    object_id: UUID
    attempt_count: int
    requires_presence_confirmation: bool
    object_key: str = field(repr=False)


def prepared_cleanup_due_at(now: datetime) -> datetime:
    return now + PREPARED_STALE_AFTER


def first_retry_due_at(now: datetime) -> datetime:
    return now + FIRST_RETRY_DELAY


def _lease_until(now: datetime, attempt_count: int) -> datetime:
    if attempt_count == 1:
        return now + SECOND_RETRY_DELAY
    return now + THIRD_RETRY_DELAY


def _safe_log(
    level: int,
    event: str,
    *,
    cleanup_id: UUID,
    tenant_id: UUID,
    status: str,
    attempt_count: int,
) -> None:
    logger.log(
        level,
        event,
        extra={
            "cleanup_id": str(cleanup_id),
            "tenant_id": str(tenant_id),
            "cleanup_status": status,
            "cleanup_attempt_count": attempt_count,
        },
    )


async def arm_upload_cleanup(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    cleanup_id: UUID,
    error_code: str = OBJECT_STORAGE_ERROR_CODE,
    now: datetime | None = None,
) -> None:
    """Move a prepared intent to pending after a confirmed request failure."""

    current = now or datetime.now(UTC)
    async with session.begin():
        cleanup = await get_upload_cleanup_for_update(
            session,
            tenant_id=tenant_id,
            cleanup_id=cleanup_id,
        )
        if cleanup is None:
            raise KnowledgeUploadCleanupUnavailableError
        if cleanup.status in {"referenced", "succeeded", "exhausted"}:
            return
        mark_upload_cleanup_pending(
            cleanup,
            next_attempt_at=first_retry_due_at(current),
            error_code=error_code,
            now=current,
        )
        await session.flush()
        attempt_count = cleanup.attempt_count
    _safe_log(
        logging.WARNING,
        "knowledge_upload_cleanup_pending",
        cleanup_id=cleanup_id,
        tenant_id=tenant_id,
        status="pending",
        attempt_count=attempt_count,
    )


async def mark_inline_cleanup_succeeded(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    cleanup_id: UUID,
    now: datetime | None = None,
) -> None:
    """Record a safe request-time delete and atomically release its quota hold."""

    current = now or datetime.now(UTC)
    async with session.begin():
        cleanup = await get_upload_cleanup_for_update(
            session,
            tenant_id=tenant_id,
            cleanup_id=cleanup_id,
        )
        if cleanup is None:
            raise KnowledgeUploadCleanupUnavailableError
        if cleanup.status in {"referenced", "exhausted"}:
            return
        if cleanup.status != "succeeded":
            mark_upload_cleanup_succeeded(cleanup, now=current)
        await release_upload_reservation_for_cleanup(
            session,
            tenant_id=tenant_id,
            cleanup_id=cleanup_id,
        )
        await session.flush()
        attempt_count = cleanup.attempt_count
    _safe_log(
        logging.INFO,
        "knowledge_upload_cleanup_succeeded",
        cleanup_id=cleanup_id,
        tenant_id=tenant_id,
        status="succeeded",
        attempt_count=attempt_count,
    )


async def _claim_due_cleanup(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    cleanup_id: UUID,
    now: datetime,
) -> CleanupReplayResult | _CleanupClaim:
    async with session.begin():
        cleanup = await get_upload_cleanup_for_update(
            session,
            tenant_id=tenant_id,
            cleanup_id=cleanup_id,
        )
        if cleanup is None:
            raise KnowledgeUploadCleanupUnavailableError
        if cleanup.status == "referenced":
            await release_upload_reservation_for_cleanup(
                session,
                tenant_id=tenant_id,
                cleanup_id=cleanup_id,
            )
            return CleanupReplayResult(
                cleanup_id=cleanup.id,
                tenant_id=cleanup.tenant_id,
                outcome="noop_referenced",
                attempt_count=cleanup.attempt_count,
            )
        if cleanup.status == "succeeded":
            await release_upload_reservation_for_cleanup(
                session,
                tenant_id=tenant_id,
                cleanup_id=cleanup_id,
            )
            return CleanupReplayResult(
                cleanup_id=cleanup.id,
                tenant_id=cleanup.tenant_id,
                outcome="noop_succeeded",
                attempt_count=cleanup.attempt_count,
            )
        if cleanup.status == "exhausted":
            return CleanupReplayResult(
                cleanup_id=cleanup.id,
                tenant_id=cleanup.tenant_id,
                outcome="exhausted",
                attempt_count=cleanup.attempt_count,
            )
        if cleanup.next_attempt_at is None or cleanup.next_attempt_at > now:
            return CleanupReplayResult(
                cleanup_id=cleanup.id,
                tenant_id=cleanup.tenant_id,
                outcome="not_due",
                attempt_count=cleanup.attempt_count,
            )
        if cleanup.attempt_count >= MAX_RECONCILIATION_ATTEMPTS:
            mark_upload_cleanup_exhausted(
                cleanup,
                error_code=cleanup.last_error_code or OBJECT_STORAGE_ERROR_CODE,
                now=now,
            )
            await session.flush()
            result = CleanupReplayResult(
                cleanup_id=cleanup.id,
                tenant_id=cleanup.tenant_id,
                outcome="exhausted",
                attempt_count=cleanup.attempt_count,
            )
            _safe_log(
                logging.ERROR,
                "knowledge_upload_cleanup_exhausted",
                cleanup_id=cleanup.id,
                tenant_id=cleanup.tenant_id,
                status="exhausted",
                attempt_count=cleanup.attempt_count,
            )
            return result

        typed_key = knowledge_raw_key(
            tenant_id=cleanup.tenant_id,
            source_id=cleanup.source_id,
            object_id=cleanup.object_id,
        )
        if typed_key.value != cleanup.object_key:
            cleanup.attempt_count = MAX_RECONCILIATION_ATTEMPTS
            mark_upload_cleanup_exhausted(
                cleanup,
                error_code=KEY_MISMATCH_ERROR_CODE,
                now=now,
            )
            await session.flush()
            result = CleanupReplayResult(
                cleanup_id=cleanup.id,
                tenant_id=cleanup.tenant_id,
                outcome="exhausted",
                attempt_count=cleanup.attempt_count,
            )
            _safe_log(
                logging.ERROR,
                "knowledge_upload_cleanup_exhausted",
                cleanup_id=cleanup.id,
                tenant_id=cleanup.tenant_id,
                status="exhausted",
                attempt_count=cleanup.attempt_count,
            )
            return result

        requires_presence_confirmation = (
            cleanup.status == "prepared"
            or cleanup.last_error_code == PUT_OUTCOME_AMBIGUOUS_ERROR_CODE
        )
        if cleanup.status == "prepared" and cleanup.last_error_code is None:
            cleanup.last_error_code = PUT_OUTCOME_AMBIGUOUS_ERROR_CODE

        cleanup.attempt_count += 1
        cleanup.status = "pending"
        cleanup.next_attempt_at = _lease_until(now, cleanup.attempt_count)
        cleanup.updated_at = now
        await session.flush()
        return _CleanupClaim(
            cleanup_id=cleanup.id,
            tenant_id=cleanup.tenant_id,
            source_id=cleanup.source_id,
            object_id=cleanup.object_id,
            object_key=cleanup.object_key,
            attempt_count=cleanup.attempt_count,
            requires_presence_confirmation=requires_presence_confirmation,
        )


async def _record_failed_attempt(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    cleanup_id: UUID,
    error_code: str,
    now: datetime,
) -> CleanupReplayResult:
    async with session.begin():
        cleanup = await get_upload_cleanup_for_update(
            session,
            tenant_id=tenant_id,
            cleanup_id=cleanup_id,
        )
        if cleanup is None:
            raise KnowledgeUploadCleanupUnavailableError from None
        if cleanup.status in {"referenced", "succeeded"}:
            outcome: CleanupReplayOutcome = (
                "noop_referenced" if cleanup.status == "referenced" else "noop_succeeded"
            )
            await release_upload_reservation_for_cleanup(
                session,
                tenant_id=tenant_id,
                cleanup_id=cleanup_id,
            )
            return CleanupReplayResult(
                cleanup_id=cleanup.id,
                tenant_id=cleanup.tenant_id,
                outcome=outcome,
                attempt_count=cleanup.attempt_count,
            )
        if cleanup.status == "exhausted":
            return CleanupReplayResult(
                cleanup_id=cleanup.id,
                tenant_id=cleanup.tenant_id,
                outcome="exhausted",
                attempt_count=cleanup.attempt_count,
            )

        if cleanup.attempt_count >= MAX_RECONCILIATION_ATTEMPTS:
            mark_upload_cleanup_exhausted(
                cleanup,
                error_code=error_code,
                now=now,
            )
            outcome = "exhausted"
            log_level = logging.ERROR
            log_event = "knowledge_upload_cleanup_exhausted"
        else:
            cleanup.status = "pending"
            cleanup.last_error_code = error_code
            cleanup.updated_at = now
            outcome = "retry_scheduled"
            log_level = logging.WARNING
            log_event = "knowledge_upload_cleanup_pending"
        await session.flush()
        attempt_count = cleanup.attempt_count

    _safe_log(
        log_level,
        log_event,
        cleanup_id=cleanup_id,
        tenant_id=tenant_id,
        status="exhausted" if outcome == "exhausted" else "pending",
        attempt_count=attempt_count,
    )
    return CleanupReplayResult(
        cleanup_id=cleanup_id,
        tenant_id=tenant_id,
        outcome=outcome,
        attempt_count=attempt_count,
    )


async def reconcile_upload_cleanup(
    session: AsyncSession,
    *,
    storage: ObjectStorage,
    tenant_id: UUID,
    cleanup_id: UUID,
    now: datetime | None = None,
) -> CleanupReplayResult:
    """Replay one cleanup obligation with bounded, idempotent deletion."""

    current = now or datetime.now(UTC)
    claim_or_result = await _claim_due_cleanup(
        session,
        tenant_id=tenant_id,
        cleanup_id=cleanup_id,
        now=current,
    )
    if isinstance(claim_or_result, CleanupReplayResult):
        return claim_or_result

    claim = claim_or_result
    key = knowledge_raw_key(
        tenant_id=claim.tenant_id,
        source_id=claim.source_id,
        object_id=claim.object_id,
    )

    if claim.requires_presence_confirmation:
        try:
            object_visible = await run_in_threadpool(storage.exists, key)
        except ObjectStorageError:
            return await _record_failed_attempt(
                session,
                tenant_id=tenant_id,
                cleanup_id=cleanup_id,
                error_code=PUT_OUTCOME_AMBIGUOUS_ERROR_CODE,
                now=datetime.now(UTC),
            )

        if not object_visible:
            return await _record_failed_attempt(
                session,
                tenant_id=tenant_id,
                cleanup_id=cleanup_id,
                error_code=PUT_OUTCOME_AMBIGUOUS_ERROR_CODE,
                now=datetime.now(UTC),
            )

    try:
        await run_in_threadpool(storage.delete_object, key)
    except ObjectStorageError:
        return await _record_failed_attempt(
            session,
            tenant_id=tenant_id,
            cleanup_id=cleanup_id,
            error_code=OBJECT_STORAGE_ERROR_CODE,
            now=datetime.now(UTC),
        )

    success_time = datetime.now(UTC)
    async with session.begin():
        cleanup = await get_upload_cleanup_for_update(
            session,
            tenant_id=tenant_id,
            cleanup_id=cleanup_id,
        )
        if cleanup is None:
            raise KnowledgeUploadCleanupUnavailableError
        if cleanup.status == "referenced":
            await release_upload_reservation_for_cleanup(
                session,
                tenant_id=tenant_id,
                cleanup_id=cleanup_id,
            )
            return CleanupReplayResult(
                cleanup_id=cleanup.id,
                tenant_id=cleanup.tenant_id,
                outcome="noop_referenced",
                attempt_count=cleanup.attempt_count,
            )
        if cleanup.status != "succeeded":
            mark_upload_cleanup_succeeded(cleanup, now=success_time)
        await release_upload_reservation_for_cleanup(
            session,
            tenant_id=tenant_id,
            cleanup_id=cleanup_id,
        )
        await session.flush()
        attempt_count = cleanup.attempt_count
    _safe_log(
        logging.INFO,
        "knowledge_upload_cleanup_succeeded",
        cleanup_id=cleanup_id,
        tenant_id=tenant_id,
        status="succeeded",
        attempt_count=attempt_count,
    )
    return CleanupReplayResult(
        cleanup_id=cleanup_id,
        tenant_id=tenant_id,
        outcome="succeeded",
        attempt_count=attempt_count,
    )


async def reconcile_due_upload_cleanups(
    session: AsyncSession,
    *,
    storage: ObjectStorage,
    now: datetime | None = None,
    limit: int = 100,
) -> tuple[CleanupReplayResult, ...]:
    """Deterministically sweep due internal cleanup IDs without exposing object keys."""

    current = now or datetime.now(UTC)
    async with session.begin():
        due = await list_due_upload_cleanup_ids(session, now=current, limit=limit)

    results: list[CleanupReplayResult] = []
    for tenant_id, cleanup_id in due:
        results.append(
            await reconcile_upload_cleanup(
                session,
                storage=storage,
                tenant_id=tenant_id,
                cleanup_id=cleanup_id,
                now=current,
            )
        )
    return tuple(results)
