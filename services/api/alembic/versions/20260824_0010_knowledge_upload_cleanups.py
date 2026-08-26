"""Add durable cleanup intents for cross-store knowledge uploads.

Revision ID: 20260824_0010
Revises: 20260819_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260824_0010"
down_revision: str | Sequence[str] | None = "20260819_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "knowledge_upload_cleanups",
        sa.Column(
            "id",
            UUID,
            primary_key=True,
            nullable=False,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("tenant_id", UUID, nullable=False),
        # Intentionally not foreign keys: the cleanup obligation exists before
        # a knowledge_sources row and a failed upload may never create that row.
        sa.Column("source_id", UUID, nullable=False),
        sa.Column("object_id", UUID, nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'prepared'"),
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('prepared', 'pending', 'referenced', 'succeeded', 'exhausted')",
            name="ck_knowledge_upload_cleanups_status",
        ),
        sa.CheckConstraint(
            "attempt_count BETWEEN 0 AND 3",
            name="ck_knowledge_upload_cleanups_attempt_count",
        ),
        sa.CheckConstraint(
            "((status IN ('prepared', 'pending') "
            "AND next_attempt_at IS NOT NULL AND resolved_at IS NULL) OR "
            "(status IN ('referenced', 'succeeded', 'exhausted') "
            "AND next_attempt_at IS NULL AND resolved_at IS NOT NULL))",
            name="ck_knowledge_upload_cleanups_state_timestamps",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_knowledge_upload_cleanups_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "source_id",
            name="uq_knowledge_upload_cleanups_tenant_source",
        ),
        sa.UniqueConstraint(
            "object_key",
            name="uq_knowledge_upload_cleanups_object_key",
        ),
    )
    op.create_index(
        "ix_knowledge_upload_cleanups_tenant_status_due",
        "knowledge_upload_cleanups",
        ["tenant_id", "status", "next_attempt_at"],
    )
    op.create_index(
        "ix_knowledge_upload_cleanups_status_due",
        "knowledge_upload_cleanups",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    unresolved = op.get_bind().execute(
        sa.text(
            """
            SELECT count(*)
            FROM knowledge_upload_cleanups
            WHERE status IN ('prepared', 'pending', 'exhausted')
            """
        )
    ).scalar_one()
    if int(unresolved) != 0:
        raise RuntimeError(
            "Cannot downgrade 20260824_0010 while unresolved knowledge upload "
            "cleanup obligations exist. Resolve prepared, pending, and exhausted "
            "rows before rollback."
        )

    op.drop_index(
        "ix_knowledge_upload_cleanups_status_due",
        table_name="knowledge_upload_cleanups",
    )
    op.drop_index(
        "ix_knowledge_upload_cleanups_tenant_status_due",
        table_name="knowledge_upload_cleanups",
    )
    op.drop_table("knowledge_upload_cleanups")
