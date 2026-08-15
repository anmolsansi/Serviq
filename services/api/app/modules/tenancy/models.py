"""ORM mappings for the frozen membership and RBAC tables."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Membership(Base):
    __tablename__ = "memberships"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_invitation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))
    tenant_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), nullable=True)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class RolePermission(Base):
    __tablename__ = "role_permissions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))
    role_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("roles.id"), nullable=False)
    permission_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class MembershipRole(Base):
    __tablename__ = "membership_roles"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))
    membership_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("memberships.id"), nullable=False)
    role_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("roles.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
