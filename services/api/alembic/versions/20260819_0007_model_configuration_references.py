"""Add deletion-protection registry for model configurations.

Revision ID: 20260819_0007
Revises: 20260815_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260819_0007"
down_revision: str | Sequence[str] | None = "20260815_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "model_configuration_references",
        sa.Column(
            "id",
            UUID,
            primary_key=True,
            nullable=False,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("model_configuration_id", UUID, nullable=False),
        sa.Column("reference_kind", sa.Text(), nullable=False),
        sa.Column("reference_id", UUID, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "char_length(reference_kind) BETWEEN 1 AND 80",
            name="ck_model_configuration_references_kind_length",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_model_configuration_references_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["model_configuration_id"],
            ["model_configurations.id"],
            name="fk_model_configuration_references_model_configuration",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "model_configuration_id",
            "reference_kind",
            "reference_id",
            name="uq_model_configuration_references_source",
        ),
    )
    op.create_index(
        "ix_model_configuration_references_tenant_model",
        "model_configuration_references",
        ["tenant_id", "model_configuration_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_model_configuration_references_tenant_model",
        table_name="model_configuration_references",
    )
    op.drop_table("model_configuration_references")
