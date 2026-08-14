"""Single SQLAlchemy declarative metadata root for Serviq API models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class whose metadata is owned by Alembic and future API models."""
