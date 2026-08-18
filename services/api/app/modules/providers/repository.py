"""Tenant-scoped persistence operations for BYOK provider and model metadata."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.providers.models import (
    ModelConfiguration,
    ModelConfigurationReference,
    ProviderConnection,
)


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


async def find_provider_connection_for_update(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    provider_connection_id: UUID,
) -> ProviderConnection | None:
    # `populate_existing=True` is critical for callers that read this row earlier in
    # the same Session, perform external work outside the transaction, and then lock
    # it again. Without it SQLAlchemy may reuse identity-map field values that were
    # loaded before another transaction rotated the credential.
    result = await session.execute(
        select(ProviderConnection)
        .where(
            ProviderConnection.id == provider_connection_id,
            ProviderConnection.tenant_id == tenant_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
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


async def list_model_configurations(
    session: AsyncSession,
    *,
    tenant_id: UUID,
) -> tuple[ModelConfiguration, ...]:
    result = await session.execute(
        select(ModelConfiguration)
        .where(ModelConfiguration.tenant_id == tenant_id)
        .order_by(ModelConfiguration.created_at, ModelConfiguration.id)
    )
    return tuple(result.scalars().all())


async def find_model_configuration_for_update(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    model_configuration_id: UUID,
) -> ModelConfiguration | None:
    result = await session.execute(
        select(ModelConfiguration)
        .where(
            ModelConfiguration.id == model_configuration_id,
            ModelConfiguration.tenant_id == tenant_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


def add_model_configuration(
    session: AsyncSession,
    *,
    model_configuration_id: UUID,
    tenant_id: UUID,
    provider_connection_id: UUID,
    alias: str,
    upstream_model: str,
    purpose: str,
    enabled: bool,
    now: datetime,
) -> ModelConfiguration:
    configuration = ModelConfiguration(
        id=model_configuration_id,
        tenant_id=tenant_id,
        provider_connection_id=provider_connection_id,
        alias=alias,
        upstream_model=upstream_model,
        purpose=purpose,
        enabled=enabled,
        created_at=now,
        updated_at=now,
    )
    session.add(configuration)
    return configuration


async def count_model_configuration_references(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    model_configuration_id: UUID,
) -> int:
    result = await session.execute(
        select(func.count(ModelConfigurationReference.id)).where(
            ModelConfigurationReference.tenant_id == tenant_id,
            ModelConfigurationReference.model_configuration_id == model_configuration_id,
        )
    )
    return int(result.scalar_one())


async def delete_model_configuration(
    session: AsyncSession,
    *,
    configuration: ModelConfiguration,
) -> None:
    await session.delete(configuration)
    await session.flush()
