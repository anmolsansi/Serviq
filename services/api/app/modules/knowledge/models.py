"""ORM mappings for tenant-owned knowledge metadata and upload cleanup state."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"))
    source_type: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    source_uri: Mapped[str | None] = mapped_column(Text)
    object_key: Mapped[str | None] = mapped_column(Text)
    access_scope: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    sync_version: Mapped[int] = mapped_column(Integer)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class KnowledgeUploadCleanup(Base):
    """Internal durable obligation for raw-object cleanup/reconciliation."""

    __tablename__ = "knowledge_upload_cleanups"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"))
    source_id: Mapped[UUID]
    object_id: Mapped[UUID]
    object_key: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(Integer)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
