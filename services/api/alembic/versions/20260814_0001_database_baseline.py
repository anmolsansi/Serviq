"""Establish Alembic persistence baseline without product tables.

Revision ID: 20260814_0001
Revises: None
"""

revision: str = "20260814_0001"
down_revision: None = None
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    """Intentionally create no Serviq product table."""


def downgrade() -> None:
    """Intentionally remove no Serviq product table."""
