"""Knowledge source registration, upload durability, quota, and capability checks."""

from datetime import UTC, datetime
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
from app.modules.knowledge.cleanup import (
    SOURCE_PERSISTENCE_ERROR_CODE,
    arm_upload_cleanup,
    mark_inline_cleanup_succeeded,
    prepared_cleanup_due_at,
)
from app.modules.knowledge.errors import KnowledgeSourceForbiddenError
from app.modules.knowledge.models import KnowledgeSource
from app.modules.knowledge.quota import (
    assert_source_capacity,
    reconcile_legacy_file_sizes,
    release_unlinked_reservation,
    reserve_file_upload,
)
from app.modules.knowledge.repository import (
    add_file_knowledge_source,
    add_knowledge_source,
    add_upload_cleanup_intent,
    bind_upload_reservation_to_cleanup,
    expire_upload_concurrency_lease_for_cleanup,
    get_upload_cleanup_for_update,
    list_knowledge_sources,
    mark_upload_cleanup_referenced,
    release_upload_reservation,
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
    """Register URL/sitemap metadata while enforcing the total tenant source cap."""

    async with session.begin():
        await _require_permission(session, user_id=user_id, tenant_id=tenant_id)
        now = datetime.now(UTC)
        await assert_source_capacity(session, tenant_id=tenant_id, now=now)
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
    """Create a quota-reserved file source without allowing an untracked raw object."""

    await _require_permission(session, user_id=user_id, tenant_id=tenant_id)
    # Permission resolution performs reads and therefore opens an implicit SQLAlchemy
    # transaction. Close it before the explicit durability transactions below.
    await session.rollback()
    validated = await validate_upload(upload, source_type=source_type)

    # Migration 0011 intentionally does not perform network I/O. Existing file rows
    # are measured through typed HEAD calls here before new bytes can be admitted.
    await reconcile_legacy_file_sizes(session, storage=storage, tenant_id=tenant_id)

    source_id = uuid4()
    reservation = await reserve_file_upload(
        session,
        tenant_id=tenant_id,
        source_id=source_id,
        reserved_bytes=validated.size,
    )
    object_id = uuid4()
    cleanup_id = uuid4()
    key = knowledge_raw_key(
        tenant_id=tenant_id,
        source_id=source_id,
        object_id=object_id,
    )

    prepared_at = datetime.now(UTC)
    try:
        async with session.begin():
            add_upload_cleanup_intent(
                session,
                cleanup_id=cleanup_id,
                tenant_id=tenant_id,
                source_id=source_id,
                object_id=object_id,
                object_key=key.value,
                next_attempt_at=prepared_cleanup_due_at(prepared_at),
                now=prepared_at,
            )
            await bind_upload_reservation_to_cleanup(
                session,
                tenant_id=tenant_id,
                reservation_id=reservation.reservation_id,
                cleanup_id=cleanup_id,
                now=prepared_at,
            )
            await session.flush()
    except Exception:
        # No PUT is permitted before this transaction commits. If DB recovery is
        # unavailable, the still-unlinked reservation self-reclaims after 10 minutes.
        try:
            await release_unlinked_reservation(
                session,
                tenant_id=tenant_id,
                reservation_id=reservation.reservation_id,
            )
        except Exception:
            await session.rollback()
        raise

    try:
        await run_in_threadpool(
            storage.put_object,
            key,
            upload.file,
            content_type=validated.content_type,
            metadata={"original-filename": validated.original_filename},
        )
    except ObjectStorageError:
        await _best_effort_failed_upload_cleanup(
            session,
            storage=storage,
            tenant_id=tenant_id,
            cleanup_id=cleanup_id,
            key=key,
            put_outcome_confirmed=False,
        )
        raise

    try:
        async with session.begin():
            cleanup = await get_upload_cleanup_for_update(
                session,
                tenant_id=tenant_id,
                cleanup_id=cleanup_id,
            )
            if cleanup is None or cleanup.status != "prepared":
                raise RuntimeError("Knowledge upload cleanup is not in the prepared state.")

            now = datetime.now(UTC)
            source = add_file_knowledge_source(
                session,
                source_id=source_id,
                tenant_id=tenant_id,
                source_type=source_type,
                name=name,
                object_key=key.value,
                object_size_bytes=validated.size,
                access_scope=access_scope,
                created_by=user_id,
                now=now,
            )
            mark_upload_cleanup_referenced(cleanup, now=now)
            await release_upload_reservation(
                session,
                tenant_id=tenant_id,
                reservation_id=reservation.reservation_id,
            )
            await session.flush()
            view = _to_view(source)
    except Exception:
        await _best_effort_failed_upload_cleanup(
            session,
            storage=storage,
            tenant_id=tenant_id,
            cleanup_id=cleanup_id,
            key=key,
            put_outcome_confirmed=True,
        )
        raise

    return view


async def _best_effort_failed_upload_cleanup(
    session: AsyncSession,
    *,
    storage: ObjectStorage,
    tenant_id: UUID,
    cleanup_id: UUID,
    key: KnowledgeRawObjectKey,
    put_outcome_confirmed: bool,
) -> None:
    """Try immediate cleanup without hiding the original upload failure.

    Once the request is known to be failing, its active-concurrency lease is ended
    best-effort. The linked reservation itself remains charged against byte/source
    quota until object cleanup is confirmed, preserving the durable safety boundary.
    """

    try:
        current = datetime.now(UTC)
        async with session.begin():
            await expire_upload_concurrency_lease_for_cleanup(
                session,
                tenant_id=tenant_id,
                cleanup_id=cleanup_id,
                now=current,
            )
            await session.flush()
    except Exception:
        # A crash/DB outage is safe: the original 10-minute lease bounds temporary
        # over-blocking and the linked reservation still cannot escape quota.
        await session.rollback()

    if put_outcome_confirmed:
        try:
            await arm_upload_cleanup(
                session,
                tenant_id=tenant_id,
                cleanup_id=cleanup_id,
                error_code=SOURCE_PERSISTENCE_ERROR_CODE,
            )
        except Exception:
            # The pre-existing `prepared` row remains the durable obligation and
            # becomes sweepable at its stale-preparation deadline.
            await session.rollback()

    try:
        await run_in_threadpool(storage.delete_object, key)
    except ObjectStorageError:
        return

    if not put_outcome_confirmed:
        # Do not terminalize an ambiguous PUT from request-time DELETE alone.
        return

    try:
        await mark_inline_cleanup_succeeded(
            session,
            tenant_id=tenant_id,
            cleanup_id=cleanup_id,
        )
    except Exception:
        # A later idempotent replay can delete the already-absent object again.
        await session.rollback()


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
