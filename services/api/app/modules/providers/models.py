"""ORM mappings for provider and model metadata created by OPE-289."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class ProviderMetadataBase(DeclarativeBase):
    """Declarative registry for the provider metadata mappings."""


class ProviderConnection(ProviderMetadataBase):
    __tablename__ = "provider_connections"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"))
    provider: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    secret_ref: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ModelConfiguration(ProviderMetadataBase):
    __tablename__ = "model_configurations"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"))
    provider_connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("provider_connections.id", ondelete="RESTRICT")
    )
    alias: Mapped[str] = mapped_column(Text)
    upstream_model: Mapped[str] = mapped_column(Text)
    purpose: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
