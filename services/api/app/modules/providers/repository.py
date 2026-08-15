"""Tenant-scoped persistence operations for BYOK provider metadata."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.providers.models import ModelConfiguration, ProviderConnection


async def list_provider_connections(
    session: AsyncSession,
    *,
    tenant_id: UUID,
) -> tuple[ProviderConnection, ...]:
    result = await session.execute(
        select(ProviderConnection)
        .where(ProviderConnection.tenant_id == tenant_id)
        .order_by(ProviderConnection.created_at, ProviderConnection.id)
    )
    return tuple(result.scalars().all())


async def find_provider_connection(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    provider_connection_id: UUID,
) -> ProviderConnection | None:
    result = await session.execute(
        select(ProviderConnection).where(
            ProviderConnection.id == provider_connection_id,
            ProviderConnection.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


def add_provider_connection(
    session: AsyncSession,
    *,
    provider_connection_id: UUID,
    tenant_id: UUID,
    provider: str,
    display_name: str,
    secret_ref: str,
    created_by: UUID,
    now: datetime,
) -> ProviderConnection:
    connection = ProviderConnection(
        id=provider_connection_id,
        tenant_id=tenant_id,
        provider=provider,
        display_name=display_name,
        secret_ref=secret_ref,
        status="untested",
        last_tested_at=None,
        last_error_code=None,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    session.add(connection)
    return connection


async def count_model_references(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    provider_connection_id: UUID,
) -> int:
    result = await session.execute(
        select(func.count(ModelConfiguration.id)).where(
            ModelConfiguration.tenant_id == tenant_id,
            ModelConfiguration.provider_connection_id == provider_connection_id,
        )
    )
    return int(result.scalar_one())


async def delete_provider_connection(
    session: AsyncSession,
    *,
    connection: ProviderConnection,
) -> None:
    await session.delete(connection)
    await session.flush()
