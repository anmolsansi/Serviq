"""Add authoritative knowledge upload quota accounting.

Revision ID: 20260828_0011
Revises: 20260824_0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260828_0011"
down_revision: str | Sequence[str] | None = "20260824_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
_MAX_FILE_BYTES = 25 * 1024 * 1024


def upgrade() -> None:
    op.add_column(
        "knowledge_sources",
        sa.Column("object_size_bytes", sa.BigInteger(), nullable=True),
    )
    op.create_check_constraint(
        "ck_knowledge_sources_object_size_bytes",
        "knowledge_sources",
        f"object_size_bytes IS NULL OR (object_size_bytes BETWEEN 0 AND {_MAX_FILE_BYTES})",
    )

    op.create_table(
        "knowledge_upload_reservations",
        sa.Column(
            "id",
            UUID,
            primary_key=True,
            nullable=False,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("source_id", UUID, nullable=False),
        sa.Column("reserved_bytes", sa.BigInteger(), nullable=False),
        sa.Column("cleanup_id", UUID, nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
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
            f"reserved_bytes BETWEEN 0 AND {_MAX_FILE_BYTES}",
            name="ck_knowledge_upload_reservations_reserved_bytes",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_knowledge_upload_reservations_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "source_id",
            name="uq_knowledge_upload_reservations_tenant_source",
        ),
        sa.UniqueConstraint(
            "cleanup_id",
            name="uq_knowledge_upload_reservations_cleanup_id",
        ),
    )
    op.create_index(
        "ix_knowledge_upload_reservations_tenant_lease",
        "knowledge_upload_reservations",
        ["tenant_id", "lease_expires_at"],
    )
    op.create_index(
        "ix_knowledge_upload_reservations_tenant_cleanup",
        "knowledge_upload_reservations",
        ["tenant_id", "cleanup_id"],
    )


def downgrade() -> None:
    reservations = op.get_bind().execute(
        sa.text("SELECT count(*) FROM knowledge_upload_reservations")
    ).scalar_one()
    if int(reservations) != 0:
        raise RuntimeError(
            "Cannot downgrade 20260828_0011 while knowledge upload reservations exist. "
            "Resolve every reservation against its source/cleanup outcome first."
        )

    op.drop_index(
        "ix_knowledge_upload_reservations_tenant_cleanup",
        table_name="knowledge_upload_reservations",
    )
    op.drop_index(
        "ix_knowledge_upload_reservations_tenant_lease",
        table_name="knowledge_upload_reservations",
    )
    op.drop_table("knowledge_upload_reservations")
    op.drop_constraint(
        "ck_knowledge_sources_object_size_bytes",
        "knowledge_sources",
        type_="check",
    )
    op.drop_column("knowledge_sources", "object_size_bytes")
