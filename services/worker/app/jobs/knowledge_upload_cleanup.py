"""Bounded durable reconciliation for failed knowledge-upload raw objects."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.object_storage import ObjectStorageError, RawObjectStorage

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 20
MAX_BATCH_SIZE = 100
DEFAULT_POLL_SECONDS = 30.0
MAX_RECONCILIATION_ATTEMPTS = 3
SECOND_RETRY_DELAY = timedelta(minutes=5)
THIRD_RETRY_DELAY = timedelta(minutes=30)
OBJECT_STORAGE_ERROR_CODE = "OBJECT_STORAGE_UNAVAILABLE"
PUT_OUTCOME_AMBIGUOUS_ERROR_CODE = "OBJECT_STORAGE_PUT_OUTCOME_AMBIGUOUS"
KEY_MISMATCH_ERROR_CODE = "KNOWLEDGE_UPLOAD_CLEANUP_KEY_MISMATCH"

CleanupOutcome = Literal["succeeded", "retry_scheduled", "exhausted"]

_CLAIM_DUE = text(
    """
    SELECT id, tenant_id, source_id, object_id, object_key,
           status, attempt_count, last_error_code
    FROM knowledge_upload_cleanups
    WHERE status IN ('prepared', 'pending')
      AND next_attempt_at <= :now
    ORDER BY next_attempt_at ASC, id ASC
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
    """
)

_MARK_CLAIMED = text(
    """
    UPDATE knowledge_upload_cleanups
    SET status = 'pending',
        attempt_count = :attempt_count,
        next_attempt_at = :next_attempt_at,
        last_error_code = :last_error_code,
        updated_at = :now
    WHERE id = :cleanup_id
      AND tenant_id = :tenant_id
      AND status IN ('prepared', 'pending')
    """
)

_MARK_EXHAUSTED = text(
    """
    UPDATE knowledge_upload_cleanups
    SET status = 'exhausted',
        attempt_count = :attempt_count,
        next_attempt_at = NULL,
        last_error_code = :error_code,
        resolved_at = :now,
        updated_at = :now
    WHERE id = :cleanup_id
      AND tenant_id = :tenant_id
      AND status IN ('prepared', 'pending')
    """
)

_RELOCK_CLEANUP = text(
    """
    SELECT status, attempt_count
    FROM knowledge_upload_cleanups
    WHERE id = :cleanup_id
      AND tenant_id = :tenant_id
    FOR UPDATE
    """
)

_RECORD_RETRY = text(
    """
    UPDATE knowledge_upload_cleanups
    SET last_error_code = :error_code,
        updated_at = :now
    WHERE id = :cleanup_id
      AND tenant_id = :tenant_id
      AND status = 'pending'
    """
)

_MARK_SUCCEEDED = text(
    """
    UPDATE knowledge_upload_cleanups
    SET status = 'succeeded',
        next_attempt_at = NULL,
        last_error_code = NULL,
        resolved_at = :now,
        updated_at = :now
    WHERE id = :cleanup_id
      AND tenant_id = :tenant_id
      AND status = 'pending'
    """
)

_RELEASE_RESERVATION = text(
    """
    DELETE FROM knowledge_upload_reservations
    WHERE tenant_id = :tenant_id
      AND cleanup_id = :cleanup_id
    """
)


class KnowledgeUploadCleanupStateError(RuntimeError):
    """Stable internal error for malformed or missing durable cleanup state."""

    def __init__(self) -> None:
        super().__init__("Knowledge upload cleanup state is invalid.")


@dataclass(frozen=True, slots=True)
class CleanupClaim:
    cleanup_id: UUID
    tenant_id: UUID
    source_id: UUID
    object_id: UUID
    attempt_count: int
    requires_presence_confirmation: bool
    object_key: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class CleanupBatchResult:
    processed: int
    succeeded: int
    retry_scheduled: int
    exhausted: int


@dataclass(frozen=True, slots=True)
class _ClaimBatch:
    claims: tuple[CleanupClaim, ...]
    exhausted: int


def _safe_log(
    level: int,
    event: str,
    *,
    cleanup_id: UUID | None = None,
    tenant_id: UUID | None = None,
    attempt_count: int | None = None,
    outcome: str | None = None,
) -> None:
    extra: dict[str, object] = {}
    if cleanup_id is not None:
        extra["cleanup_id"] = str(cleanup_id)
    if tenant_id is not None:
        extra["tenant_id"] = str(tenant_id)
    if attempt_count is not None:
        extra["cleanup_attempt_count"] = attempt_count
    if outcome is not None:
        extra["cleanup_outcome"] = outcome
    logger.log(level, event, extra=extra)


def _required_uuid(value: object) -> UUID:
    if not isinstance(value, UUID):
        raise KnowledgeUploadCleanupStateError
    return value


def _required_text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise KnowledgeUploadCleanupStateError
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _required_text(value)


def _required_attempt_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise KnowledgeUploadCleanupStateError
    if not 0 <= value <= MAX_RECONCILIATION_ATTEMPTS:
        raise KnowledgeUploadCleanupStateError
    return value


def _knowledge_raw_key(*, tenant_id: UUID, source_id: UUID, object_id: UUID) -> str:
    return f"tenants/{tenant_id}/knowledge/{source_id}/raw/{object_id}"


def _lease_until(now: datetime, attempt_count: int) -> datetime:
    if attempt_count == 1:
        return now + SECOND_RETRY_DELAY
    return now + THIRD_RETRY_DELAY


def _decode_claim_row(row: Mapping[Any, Any]) -> tuple[CleanupClaim, str | None, str]:
    cleanup_id = _required_uuid(row.get("id"))
    tenant_id = _required_uuid(row.get("tenant_id"))
    source_id = _required_uuid(row.get("source_id"))
    object_id = _required_uuid(row.get("object_id"))
    object_key = _required_text(row.get("object_key"))
    status = _required_text(row.get("status"))
    if status not in {"prepared", "pending"}:
        raise KnowledgeUploadCleanupStateError
    attempt_count = _required_attempt_count(row.get("attempt_count"))
    last_error_code = _optional_text(row.get("last_error_code"))
    requires_presence_confirmation = (
        status == "prepared" or last_error_code == PUT_OUTCOME_AMBIGUOUS_ERROR_CODE
    )
    return (
        CleanupClaim(
            cleanup_id=cleanup_id,
            tenant_id=tenant_id,
            source_id=source_id,
            object_id=object_id,
            object_key=object_key,
            attempt_count=attempt_count,
            requires_presence_confirmation=requires_presence_confirmation,
        ),
        last_error_code,
        status,
    )


async def _claim_due_batch(
    session: AsyncSession,
    *,
    now: datetime,
    batch_size: int,
) -> _ClaimBatch:
    claims: list[CleanupClaim] = []
    exhausted = 0
    async with session.begin():
        result = await session.execute(_CLAIM_DUE, {"now": now, "batch_size": batch_size})
        rows = result.mappings().all()
        for row in rows:
            claim, last_error_code, original_status = _decode_claim_row(row)
            expected_key = _knowledge_raw_key(
                tenant_id=claim.tenant_id,
                source_id=claim.source_id,
                object_id=claim.object_id,
            )

            if claim.object_key != expected_key:
                await session.execute(
                    _MARK_EXHAUSTED,
                    {
                        "cleanup_id": claim.cleanup_id,
                        "tenant_id": claim.tenant_id,
                        "attempt_count": MAX_RECONCILIATION_ATTEMPTS,
                        "error_code": KEY_MISMATCH_ERROR_CODE,
                        "now": now,
                    },
                )
                exhausted += 1
                _safe_log(
                    logging.ERROR,
                    "knowledge_upload_cleanup_exhausted",
                    cleanup_id=claim.cleanup_id,
                    tenant_id=claim.tenant_id,
                    attempt_count=MAX_RECONCILIATION_ATTEMPTS,
                    outcome="key_mismatch",
                )
                continue

            if claim.attempt_count >= MAX_RECONCILIATION_ATTEMPTS:
                await session.execute(
                    _MARK_EXHAUSTED,
                    {
                        "cleanup_id": claim.cleanup_id,
                        "tenant_id": claim.tenant_id,
                        "attempt_count": claim.attempt_count,
                        "error_code": last_error_code or OBJECT_STORAGE_ERROR_CODE,
                        "now": now,
                    },
                )
                exhausted += 1
                _safe_log(
                    logging.ERROR,
                    "knowledge_upload_cleanup_exhausted",
                    cleanup_id=claim.cleanup_id,
                    tenant_id=claim.tenant_id,
                    attempt_count=claim.attempt_count,
                    outcome="attempts_exhausted",
                )
                continue

            attempt_count = claim.attempt_count + 1
            error_code = last_error_code
            if original_status == "prepared" and error_code is None:
                error_code = PUT_OUTCOME_AMBIGUOUS_ERROR_CODE
            await session.execute(
                _MARK_CLAIMED,
                {
                    "cleanup_id": claim.cleanup_id,
                    "tenant_id": claim.tenant_id,
                    "attempt_count": attempt_count,
                    "next_attempt_at": _lease_until(now, attempt_count),
                    "last_error_code": error_code,
                    "now": now,
                },
            )
            claims.append(
                CleanupClaim(
                    cleanup_id=claim.cleanup_id,
                    tenant_id=claim.tenant_id,
                    source_id=claim.source_id,
                    object_id=claim.object_id,
                    object_key=claim.object_key,
                    attempt_count=attempt_count,
                    requires_presence_confirmation=claim.requires_presence_confirmation,
                )
            )
    return _ClaimBatch(claims=tuple(claims), exhausted=exhausted)


async def _record_failed_attempt(
    session: AsyncSession,
    *,
    claim: CleanupClaim,
    error_code: str,
    now: datetime,
) -> CleanupOutcome:
    async with session.begin():
        result = await session.execute(
            _RELOCK_CLEANUP,
            {"cleanup_id": claim.cleanup_id, "tenant_id": claim.tenant_id},
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise KnowledgeUploadCleanupStateError
        status = _required_text(row.get("status"))
        attempt_count = _required_attempt_count(row.get("attempt_count"))

        if status == "exhausted":
            return "exhausted"
        if status in {"referenced", "succeeded"}:
            await session.execute(
                _RELEASE_RESERVATION,
                {"cleanup_id": claim.cleanup_id, "tenant_id": claim.tenant_id},
            )
            return "succeeded"
        if status != "pending":
            raise KnowledgeUploadCleanupStateError

        if attempt_count >= MAX_RECONCILIATION_ATTEMPTS:
            await session.execute(
                _MARK_EXHAUSTED,
                {
                    "cleanup_id": claim.cleanup_id,
                    "tenant_id": claim.tenant_id,
                    "attempt_count": attempt_count,
                    "error_code": error_code,
                    "now": now,
                },
            )
            outcome: CleanupOutcome = "exhausted"
        else:
            await session.execute(
                _RECORD_RETRY,
                {
                    "cleanup_id": claim.cleanup_id,
                    "tenant_id": claim.tenant_id,
                    "error_code": error_code,
                    "now": now,
                },
            )
            outcome = "retry_scheduled"

    _safe_log(
        logging.ERROR if outcome == "exhausted" else logging.WARNING,
        "knowledge_upload_cleanup_exhausted"
        if outcome == "exhausted"
        else "knowledge_upload_cleanup_retry_scheduled",
        cleanup_id=claim.cleanup_id,
        tenant_id=claim.tenant_id,
        attempt_count=claim.attempt_count,
        outcome=outcome,
    )
    return outcome


async def _record_success(
    session: AsyncSession,
    *,
    claim: CleanupClaim,
    now: datetime,
) -> CleanupOutcome:
    async with session.begin():
        result = await session.execute(
            _RELOCK_CLEANUP,
            {"cleanup_id": claim.cleanup_id, "tenant_id": claim.tenant_id},
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise KnowledgeUploadCleanupStateError
        status = _required_text(row.get("status"))
        if status == "exhausted":
            return "exhausted"
        if status == "referenced":
            raise KnowledgeUploadCleanupStateError
        if status != "succeeded":
            if status != "pending":
                raise KnowledgeUploadCleanupStateError
            await session.execute(
                _MARK_SUCCEEDED,
                {
                    "cleanup_id": claim.cleanup_id,
                    "tenant_id": claim.tenant_id,
                    "now": now,
                },
            )
        await session.execute(
            _RELEASE_RESERVATION,
            {"cleanup_id": claim.cleanup_id, "tenant_id": claim.tenant_id},
        )

    _safe_log(
        logging.INFO,
        "knowledge_upload_cleanup_succeeded",
        cleanup_id=claim.cleanup_id,
        tenant_id=claim.tenant_id,
        attempt_count=claim.attempt_count,
        outcome="succeeded",
    )
    return "succeeded"


async def _execute_claim(
    session: AsyncSession,
    storage: RawObjectStorage,
    claim: CleanupClaim,
) -> CleanupOutcome:
    if claim.requires_presence_confirmation:
        try:
            visible = await storage.exists(claim.object_key)
        except ObjectStorageError:
            return await _record_failed_attempt(
                session,
                claim=claim,
                error_code=PUT_OUTCOME_AMBIGUOUS_ERROR_CODE,
                now=datetime.now(UTC),
            )
        if not visible:
            return await _record_failed_attempt(
                session,
                claim=claim,
                error_code=PUT_OUTCOME_AMBIGUOUS_ERROR_CODE,
                now=datetime.now(UTC),
            )

    try:
        await storage.delete_object(claim.object_key)
    except ObjectStorageError:
        return await _record_failed_attempt(
            session,
            claim=claim,
            error_code=OBJECT_STORAGE_ERROR_CODE,
            now=datetime.now(UTC),
        )
    return await _record_success(session, claim=claim, now=datetime.now(UTC))


async def reconcile_due_upload_cleanups(
    session: AsyncSession,
    storage: RawObjectStorage,
    *,
    now: datetime | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> CleanupBatchResult:
    """Claim and reconcile one bounded batch without storage I/O in a DB transaction."""

    if isinstance(batch_size, bool) or not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}")
    current = now or datetime.now(UTC)
    claim_batch = await _claim_due_batch(session, now=current, batch_size=batch_size)

    succeeded = 0
    retry_scheduled = 0
    exhausted = claim_batch.exhausted
    for claim in claim_batch.claims:
        outcome = await _execute_claim(session, storage, claim)
        if outcome == "succeeded":
            succeeded += 1
        elif outcome == "retry_scheduled":
            retry_scheduled += 1
        else:
            exhausted += 1

    result = CleanupBatchResult(
        processed=len(claim_batch.claims) + claim_batch.exhausted,
        succeeded=succeeded,
        retry_scheduled=retry_scheduled,
        exhausted=exhausted,
    )
    if result.processed:
        logger.info(
            "knowledge_upload_cleanup_batch_completed",
            extra={
                "cleanup_processed_count": result.processed,
                "cleanup_succeeded_count": result.succeeded,
                "cleanup_retry_count": result.retry_scheduled,
                "cleanup_exhausted_count": result.exhausted,
            },
        )
    return result


async def run_knowledge_upload_cleanup_loop(
    session_factory: async_sessionmaker[AsyncSession],
    storage: RawObjectStorage,
    *,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    """Continuously execute bounded cleanup batches until worker cancellation."""

    if poll_seconds <= 0:
        raise ValueError("poll_seconds must be positive")
    if isinstance(batch_size, bool) or not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}")

    while True:
        try:
            async with session_factory() as session:
                await reconcile_due_upload_cleanups(
                    session,
                    storage,
                    batch_size=batch_size,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error("knowledge_upload_cleanup_loop_failed")
        await asyncio.sleep(poll_seconds)
