"""Create the generic transactional outbox persistence contract.

Revision ID: 20260902_0012
Revises: 20260828_0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260902_0012"
down_revision: str | Sequence[str] | None = "20260828_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column(
            "id",
            UUID,
            primary_key=True,
            nullable=False,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("tenant_id", UUID, nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column(
            "schema_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("aggregate_type", sa.Text(), nullable=False),
        sa.Column("aggregate_id", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("correlation_id", sa.Text(), nullable=False),
        sa.Column("causation_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'published', 'failed')",
            name="ck_outbox_events_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_outbox_events_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_outbox_events_status_next_attempt",
        "outbox_events",
        ["status", "next_attempt_at"],
    )
    op.create_index(
        "ix_outbox_events_tenant_aggregate",
        "outbox_events",
        ["tenant_id", "aggregate_type", "aggregate_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_events_tenant_aggregate", table_name="outbox_events")
    op.drop_index("ix_outbox_events_status_next_attempt", table_name="outbox_events")
    op.drop_table("outbox_events")
