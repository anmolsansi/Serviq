"""Existing workforce identity persistence mapped from Architecture v1.3."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    """ORM mapping for the frozen existing `users` table.

    OPE-281 does not create or alter this table. The mapping lets repository code use
    the schema created by OPE-277 without inventing another persistence shape.
    """

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    oidc_issuer: Mapped[str] = mapped_column(Text, nullable=False)
    oidc_subject: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
