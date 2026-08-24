"""Knowledge source registration, listing, tenant isolation, and capability checks."""

from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.core.object_storage import (
    KnowledgeRawObjectKey,
    ObjectStorage,
    ObjectStorageError,
    knowledge_raw_key,
)
from app.modules.knowledge.errors import KnowledgeSourceForbiddenError
from app.modules.knowledge.models import KnowledgeSource
from app.modules.knowledge.repository import (
    add_file_knowledge_source,
    add_knowledge_source,
    add_knowledge_upload_cleanup,
    arm_knowledge_upload_cleanup,
    get_knowledge_upload_cleanup_for_update,
    knowledge_upload_cleanup_status_counts,
    list_knowledge_sources,
    mark_knowledge_upload_cleanup_exhausted,
    mark_knowledge_upload_cleanup_referenced,
    mark_knowledge_upload_cleanup_succeeded,
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
KNOWLEDGE_UPLOAD_SOURCE_PERSISTENCE_ERROR_CODE = "KNOWLEDGE_UPLOAD_SOURCE_PERSISTENCE_FAILED"
_PREPARED_RECONCILIATION_GRACE = timedelta(minutes=15)
_FIRST_RETRY_DELAY = timedelta(seconds=30)
_MAX_RECONCILIATION_ATTEMPTS = 3

KnowledgeUploadCleanupOutcome = Literal[
    "not_due",
    "retry_scheduled",
    "succeeded",
    "exhausted",
]


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
    cleanup_id = uuid4()
    key = knowledge_raw_key(tenant_id=tenant_id, source_id=source_id, object_id=object_id)

    # Freeze the cross-store obligation before the PUT. If this transaction fails,
    # storage is never called and this request cannot create an untracked raw object.
    prepared_at = datetime.now(UTC)
    async with session.begin():
        add_knowledge_upload_cleanup(
            session,
            cleanup_id=cleanup_id,
            tenant_id=tenant_id,
            source_id=source_id,
            object_id=object_id,
            object_key=key.value,
            next_attempt_at=prepared_at + _PREPARED_RECONCILIATION_GRACE,
            now=prepared_at,
        )
        await session.flush()

    try:
        await run_in_threadpool(
            storage.put_object,
            key,
            upload.file,
            content_type=validated.content_type,
            metadata={"original-filename": validated.original_filename},
        )
    except ObjectStorageError:
        await _recover_failed_file_upload(
            session,
            storage=storage,
            tenant_id=tenant_id,
            cleanup_id=cleanup_id,
            key=key,
            error_code=ObjectStorageError.error_code,
        )
        raise

    try:
        # Source creation and cleanup ownership transition are one transaction. A
        # rollback leaves the original prepared intent available for reconciliation.
        async with session.begin():
            cleanup = await get_knowledge_upload_cleanup_for_update(
                session,
                cleanup_id=cleanup_id,
                tenant_id=tenant_id,
            )
            if cleanup is None or cleanup.status != "prepared":
                raise RuntimeError("Knowledge upload cleanup state is unavailable.")
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
            mark_knowledge_upload_cleanup_referenced(cleanup, now=now)
            await session.flush()
            view = _to_view(source)
    except Exception:
        await _recover_failed_file_upload(
            session,
            storage=storage,
            tenant_id=tenant_id,
            cleanup_id=cleanup_id,
            key=key,
            error_code=KNOWLEDGE_UPLOAD_SOURCE_PERSISTENCE_ERROR_CODE,
        )
        raise
    return view


async def reconcile_file_upload_cleanup(
    session: AsyncSession,
    *,
    storage: ObjectStorage,
    tenant_id: UUID,
    cleanup_id: UUID,
    now: datetime | None = None,
) -> KnowledgeUploadCleanupOutcome:
    """Replay one due cleanup obligation for a trusted worker/platform caller."""

    effective_now = datetime.now(UTC) if now is None else now
    await session.rollback()

    async with session.begin():
        cleanup = await get_knowledge_upload_cleanup_for_update(
            session,
            cleanup_id=cleanup_id,
            tenant_id=tenant_id,
        )
        if cleanup is None:
            return "not_due"
        if cleanup.status == "exhausted":
            return "exhausted"
        if cleanup.status not in {"prepared", "pending"}:
            return "not_due"
        if cleanup.next_attempt_at is None or cleanup.next_attempt_at > effective_now:
            return "not_due"
        if cleanup.attempt_count >= _MAX_RECONCILIATION_ATTEMPTS:
            mark_knowledge_upload_cleanup_exhausted(
                cleanup,
                error_code=ObjectStorageError.error_code,
                now=effective_now,
            )
            await session.flush()
            return "exhausted"

        cleanup.status = "pending"
        cleanup.attempt_count += 1
        attempt_count = cleanup.attempt_count
        cleanup.next_attempt_at = effective_now + _retry_delay_after_claim(attempt_count)
        cleanup.last_error_code = ObjectStorageError.error_code
        cleanup.resolved_at = None
        cleanup.updated_at = effective_now
        source_id = cleanup.source_id
        object_id = cleanup.object_id
        await session.flush()

    key = knowledge_raw_key(
        tenant_id=tenant_id,
        source_id=source_id,
        object_id=object_id,
    )
    try:
        await run_in_threadpool(storage.delete_object, key)
    except ObjectStorageError:
        failure_at = datetime.now(UTC)
        async with session.begin():
            cleanup = await get_knowledge_upload_cleanup_for_update(
                session,
                cleanup_id=cleanup_id,
                tenant_id=tenant_id,
            )
            if cleanup is None or cleanup.status != "pending":
                return "not_due"
            if cleanup.attempt_count != attempt_count:
                return "not_due"
            cleanup.last_error_code = ObjectStorageError.error_code
            cleanup.updated_at = failure_at
            if attempt_count >= _MAX_RECONCILIATION_ATTEMPTS:
                mark_knowledge_upload_cleanup_exhausted(
                    cleanup,
                    error_code=ObjectStorageError.error_code,
                    now=failure_at,
                )
                await session.flush()
                return "exhausted"
            await session.flush()
        return "retry_scheduled"

    succeeded_at = datetime.now(UTC)
    async with session.begin():
        cleanup = await get_knowledge_upload_cleanup_for_update(
            session,
            cleanup_id=cleanup_id,
            tenant_id=tenant_id,
        )
        if cleanup is None or cleanup.status != "pending":
            return "not_due"
        if cleanup.attempt_count != attempt_count:
            return "not_due"
        mark_knowledge_upload_cleanup_succeeded(cleanup, now=succeeded_at)
        await session.flush()
    return "succeeded"


async def get_file_upload_cleanup_status_counts(
    session: AsyncSession,
) -> dict[str, int]:
    """Expose only bounded status counts to trusted platform operations."""

    return await knowledge_upload_cleanup_status_counts(session)


async def _recover_failed_file_upload(
    session: AsyncSession,
    *,
    storage: ObjectStorage,
    tenant_id: UUID,
    cleanup_id: UUID,
    key: KnowledgeRawObjectKey,
    error_code: str,
) -> None:
    """Best-effort fast recovery; the pre-PUT prepared row remains the durable fallback."""

    await _best_effort_arm_cleanup(
        session,
        tenant_id=tenant_id,
        cleanup_id=cleanup_id,
        error_code=error_code,
    )

    try:
        await run_in_threadpool(storage.delete_object, key)
    except Exception:
        # Never mask the request's original failure. If delete or storage is unavailable,
        # prepared/pending state remains durable and the bounded reconciler can retry.
        return

    await _best_effort_mark_cleanup_succeeded(
        session,
        tenant_id=tenant_id,
        cleanup_id=cleanup_id,
    )


async def _best_effort_arm_cleanup(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    cleanup_id: UUID,
    error_code: str,
) -> bool:
    now = datetime.now(UTC)
    try:
        await session.rollback()
        async with session.begin():
            cleanup = await get_knowledge_upload_cleanup_for_update(
                session,
                cleanup_id=cleanup_id,
                tenant_id=tenant_id,
            )
            if cleanup is None:
                return False
            changed = arm_knowledge_upload_cleanup(
                cleanup,
                next_attempt_at=now + _FIRST_RETRY_DELAY,
                error_code=error_code,
                now=now,
            )
            await session.flush()
            return changed
    except Exception:
        await _best_effort_rollback(session)
        return False


async def _best_effort_mark_cleanup_succeeded(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    cleanup_id: UUID,
) -> bool:
    now = datetime.now(UTC)
    try:
        await session.rollback()
        async with session.begin():
            cleanup = await get_knowledge_upload_cleanup_for_update(
                session,
                cleanup_id=cleanup_id,
                tenant_id=tenant_id,
            )
            if cleanup is None:
                return False
            changed = mark_knowledge_upload_cleanup_succeeded(cleanup, now=now)
            await session.flush()
            return changed
    except Exception:
        await _best_effort_rollback(session)
        return False


async def _best_effort_rollback(session: AsyncSession) -> None:
    try:
        await session.rollback()
    except Exception:
        return


def _retry_delay_after_claim(attempt_count: int) -> timedelta:
    if attempt_count == 1:
        return timedelta(minutes=5)
    return timedelta(minutes=30)


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
