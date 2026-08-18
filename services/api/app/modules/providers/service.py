"""Provider CRUD and connectivity-test authorization/compensation rules."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limits import (
    ProviderTestRateLimiter,
    RateLimitUnavailableError,
)
from app.core.secret_store import SecretNotFoundError, TenantSecretStore
from app.modules.providers.errors import (
    ProviderConflictError,
    ProviderForbiddenError,
    ProviderNotFoundError,
    ProviderReferencedError,
    ProviderSecretCleanupError,
    ProviderTestRateLimitedError,
    ProviderTestStaleError,
    ProviderTestUnavailableError,
)
from app.modules.providers.gateway import ProviderConnectivityGateway
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
    ProviderConnectivityErrorCode,
    ProviderConnectivityView,
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


async def test_provider_connectivity(
    session: AsyncSession,
    *,
    user_id: UUID,
    tenant_id: UUID,
    provider_connection_id: UUID,
    secret_store: TenantSecretStore,
    gateway: ProviderConnectivityGateway,
    rate_limiter: ProviderTestRateLimiter,
) -> ProviderConnectivityView:
    """Run one bounded provider test without holding a database transaction open."""

    # Phase 1: authorize and capture immutable identifiers in a short transaction.
    async with session.begin():
        await _require_permission(session, user_id=user_id, tenant_id=tenant_id)
        current = await find_provider_connection(
            session,
            tenant_id=tenant_id,
            provider_connection_id=provider_connection_id,
        )
        if current is None:
            raise ProviderNotFoundError
        if current.status == "disabled":
            return ProviderConnectivityView(status="disabled", errorCode=None)
        tested_secret_ref = current.secret_ref
        tested_provider = cast(ProviderKey, current.provider)

    # Shared abuse controls run before plaintext secret resolution or any provider call.
    try:
        rate_decision = await rate_limiter.check_and_consume(
            tenant_id=tenant_id,
            user_id=user_id,
            provider_connection_id=provider_connection_id,
        )
    except RateLimitUnavailableError:
        raise ProviderTestUnavailableError from None
    if not rate_decision.allowed:
        raise ProviderTestRateLimitedError(rate_decision.retry_after_seconds or 1)

    try:
        api_key = secret_store.get_secret(tenant_id, tested_secret_ref)
    except SecretNotFoundError:
        raise ProviderTestUnavailableError from None
    except Exception:
        raise ProviderTestUnavailableError from None

    # External network/model work is deliberately outside both database transactions.
    outcome = await gateway.test(
        tenant_id=tenant_id,
        provider=tested_provider,
        api_key=api_key,
        correlation_id=f"provider-test:{provider_connection_id}:{uuid4()}",
    )
    now = datetime.now(UTC)

    # Phase 2: lock and verify the credential still matches the one that was tested.
    async with session.begin():
        connection = await find_provider_connection_for_update(
            session,
            tenant_id=tenant_id,
            provider_connection_id=provider_connection_id,
        )
        if connection is None:
            raise ProviderNotFoundError
        if connection.secret_ref != tested_secret_ref or connection.provider != tested_provider:
            raise ProviderTestStaleError
        if connection.status == "disabled":
            return ProviderConnectivityView(status="disabled", errorCode=None)

        error_code = cast(ProviderConnectivityErrorCode | None, outcome.error_code)
        connection.last_tested_at = now
        connection.updated_at = now
        if outcome.ok:
            connection.status = "active"
            connection.last_error_code = None
            error_code = None
        else:
            connection.last_error_code = error_code
            if error_code == "PROVIDER_AUTH_FAILED":
                connection.status = "invalid"
            # All other normalized failures preserve the status currently protected
            # by this row lock. Temporary upstream incidents are not credential proof.
        await session.flush()
        return ProviderConnectivityView(
            status=cast(ProviderStatus, connection.status),
            errorCode=error_code,
        )


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
