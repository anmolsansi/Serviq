"""Provider CRUD authorization and cross-store compensation rules."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secret_store import SecretNotFoundError, TenantSecretStore
from app.modules.providers.errors import (
    ProviderConflictError,
    ProviderForbiddenError,
    ProviderNotFoundError,
    ProviderReferencedError,
    ProviderSecretCleanupError,
)
from app.modules.providers.models import ProviderConnection
from app.modules.providers.repository import (
    add_provider_connection,
    count_model_references,
    delete_provider_connection,
    find_provider_connection,
    find_provider_connection_for_update,
    list_provider_connections,
)
from app.modules.providers.schemas import (
    ProviderCreateRequest,
    ProviderKey,
    ProviderStatus,
    ProviderUpdateRequest,
    ProviderView,
)
from app.modules.tenancy.errors import TenantMembershipAccessError
from app.modules.tenancy.service import resolve_tenant_membership

PROVIDER_MANAGE_PERMISSION = "ai.providers.manage"


async def list_providers(
    session: AsyncSession,
    *,
    user_id: UUID,
    tenant_id: UUID,
) -> tuple[ProviderView, ...]:
    await _require_permission(session, user_id=user_id, tenant_id=tenant_id)
    connections = await list_provider_connections(session, tenant_id=tenant_id)
    return tuple(_to_view(connection) for connection in connections)


async def get_provider(
    session: AsyncSession,
    *,
    user_id: UUID,
    tenant_id: UUID,
    provider_connection_id: UUID,
) -> ProviderView:
    await _require_permission(session, user_id=user_id, tenant_id=tenant_id)
    connection = await find_provider_connection(
        session,
        tenant_id=tenant_id,
        provider_connection_id=provider_connection_id,
    )
    if connection is None:
        raise ProviderNotFoundError
    return _to_view(connection)


async def create_provider(
    session: AsyncSession,
    *,
    user_id: UUID,
    tenant_id: UUID,
    request: ProviderCreateRequest,
    secret_store: TenantSecretStore,
) -> ProviderView:
    # Authorization is committed/closed before plaintext secret persistence so the
    # subsequent metadata transaction starts cleanly and unauthorized callers never
    # cause a secret-store write.
    async with session.begin():
        await _require_permission(session, user_id=user_id, tenant_id=tenant_id)

    secret_ref = secret_store.put_secret(tenant_id, request.api_key)
    try:
        now = datetime.now(UTC)
        async with session.begin():
            connection = add_provider_connection(
                session,
                provider_connection_id=uuid4(),
                tenant_id=tenant_id,
                provider=request.provider,
                display_name=request.display_name,
                secret_ref=secret_ref,
                created_by=user_id,
                now=now,
            )
            await session.flush()
            view = _to_view(connection)
    except IntegrityError:
        await session.rollback()
        _cleanup_new_secret(secret_store, tenant_id=tenant_id, secret_ref=secret_ref)
        raise ProviderConflictError from None
    except Exception:
        await session.rollback()
        _cleanup_new_secret(secret_store, tenant_id=tenant_id, secret_ref=secret_ref)
        raise
    return view


async def update_provider(
    session: AsyncSession,
    *,
    user_id: UUID,
    tenant_id: UUID,
    provider_connection_id: UUID,
    request: ProviderUpdateRequest,
    secret_store: TenantSecretStore,
) -> ProviderView:
    async with session.begin():
        await _require_permission(session, user_id=user_id, tenant_id=tenant_id)
        current = await find_provider_connection(
            session,
            tenant_id=tenant_id,
            provider_connection_id=provider_connection_id,
        )
        if current is None:
            raise ProviderNotFoundError

    new_secret_ref: str | None = None
    if request.api_key is not None:
        new_secret_ref = secret_store.put_secret(tenant_id, request.api_key)

    old_secret_ref: str | None = None
    try:
        async with session.begin():
            connection = await find_provider_connection_for_update(
                session,
                tenant_id=tenant_id,
                provider_connection_id=provider_connection_id,
            )
            if connection is None:
                raise ProviderNotFoundError
            if request.display_name is not None:
                connection.display_name = request.display_name
            if new_secret_ref is not None:
                # Capture the predecessor only after the row lock is held. A concurrent
                # rotation may have committed after the preflight existence check.
                old_secret_ref = connection.secret_ref
                # A connectivity test is required before a replacement key may return
                # to active; replacement therefore resets safe status metadata.
                connection.secret_ref = new_secret_ref
                connection.status = "untested"
                connection.last_tested_at = None
                connection.last_error_code = None
            connection.updated_at = datetime.now(UTC)
            await session.flush()
            view = _to_view(connection)
    except IntegrityError:
        await session.rollback()
        if new_secret_ref is not None:
            _cleanup_new_secret(
                secret_store,
                tenant_id=tenant_id,
                secret_ref=new_secret_ref,
            )
        raise ProviderConflictError from None
    except Exception:
        await session.rollback()
        if new_secret_ref is not None:
            _cleanup_new_secret(
                secret_store,
                tenant_id=tenant_id,
                secret_ref=new_secret_ref,
            )
        raise

    if old_secret_ref is not None and new_secret_ref != old_secret_ref:
        try:
            secret_store.delete_secret(tenant_id, old_secret_ref)
        except SecretNotFoundError:
            # Metadata already points to the usable new secret. Missing old material is
            # not a broken reference and there is nothing left to clean up.
            pass
        except Exception:
            raise ProviderSecretCleanupError from None
    return view


async def delete_provider(
    session: AsyncSession,
    *,
    user_id: UUID,
    tenant_id: UUID,
    provider_connection_id: UUID,
    secret_store: TenantSecretStore,
) -> None:
    async with session.begin():
        await _require_permission(session, user_id=user_id, tenant_id=tenant_id)
        connection = await find_provider_connection_for_update(
            session,
            tenant_id=tenant_id,
            provider_connection_id=provider_connection_id,
        )
        if connection is None:
            raise ProviderNotFoundError
        if await count_model_references(
            session,
            tenant_id=tenant_id,
            provider_connection_id=provider_connection_id,
        ):
            raise ProviderReferencedError
        secret_ref = connection.secret_ref
        await delete_provider_connection(session, connection=connection)

    try:
        secret_store.delete_secret(tenant_id, secret_ref)
    except SecretNotFoundError:
        pass
    except Exception:
        # Relational metadata is already safely absent, so no live model can resolve
        # this orphaned secret. Surface the cleanup failure instead of hiding it.
        raise ProviderSecretCleanupError from None


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
        raise ProviderNotFoundError from None
    if PROVIDER_MANAGE_PERMISSION not in membership.permissions:
        raise ProviderForbiddenError


def _cleanup_new_secret(
    secret_store: TenantSecretStore,
    *,
    tenant_id: UUID,
    secret_ref: str,
) -> None:
    try:
        secret_store.delete_secret(tenant_id, secret_ref)
    except SecretNotFoundError:
        return
    except Exception:
        raise ProviderSecretCleanupError from None


def _to_view(connection: ProviderConnection) -> ProviderView:
    return ProviderView(
        id=connection.id,
        provider=cast(ProviderKey, connection.provider),
        displayName=connection.display_name,
        status=cast(ProviderStatus, connection.status),
        lastTestedAt=connection.last_tested_at,
        lastErrorCode=connection.last_error_code,
        createdAt=connection.created_at,
        updatedAt=connection.updated_at,
    )
