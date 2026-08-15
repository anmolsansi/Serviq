"""Create tenant provider-connection and model-configuration metadata.

Revision ID: 20260815_0005
Revises: 20260815_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260815_0005"
down_revision: str | Sequence[str] | None = "20260815_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def _id_column() -> sa.Column[object]:
    return sa.Column(
        "id",
        UUID,
        primary_key=True,
        nullable=False,
        server_default=sa.text("uuidv7()"),
    )


def _created_at_column() -> sa.Column[object]:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


def _updated_at_column() -> sa.Column[object]:
    return sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


def upgrade() -> None:
    op.create_table(
        "provider_connections",
        _id_column(),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("secret_ref", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'untested'")),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.Text(), nullable=True),
        sa.Column("created_by", UUID, nullable=False),
        _created_at_column(),
        _updated_at_column(),
        sa.CheckConstraint(
            "provider IN ('openai', 'anthropic', 'gemini', 'openrouter')",
            name="ck_provider_connections_provider",
        ),
        sa.CheckConstraint(
            "char_length(display_name) BETWEEN 1 AND 80",
            name="ck_provider_connections_display_name_length",
        ),
        sa.CheckConstraint(
            "char_length(secret_ref) >= 1",
            name="ck_provider_connections_secret_ref_nonempty",
        ),
        sa.CheckConstraint(
            "status IN ('untested', 'active', 'invalid', 'disabled')",
            name="ck_provider_connections_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_provider_connections_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_provider_connections_created_by_users",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "display_name",
            name="uq_provider_connections_tenant_display_name",
        ),
    )
    op.create_index(
        "ix_provider_connections_tenant_provider_status",
        "provider_connections",
        ["tenant_id", "provider", "status"],
    )

    op.create_table(
        "model_configurations",
        _id_column(),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("provider_connection_id", UUID, nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("upstream_model", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        _created_at_column(),
        _updated_at_column(),
        sa.CheckConstraint(
            "char_length(alias) BETWEEN 1 AND 80",
            name="ck_model_configurations_alias_length",
        ),
        sa.CheckConstraint(
            "char_length(upstream_model) BETWEEN 1 AND 160",
            name="ck_model_configurations_upstream_model_length",
        ),
        sa.CheckConstraint(
            "purpose IN ('generation', 'embedding', 'rerank')",
            name="ck_model_configurations_purpose",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_model_configurations_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["provider_connection_id"],
            ["provider_connections.id"],
            name="fk_model_configurations_provider_connection_id_provider_connections",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "alias",
            name="uq_model_configurations_tenant_alias",
        ),
    )
    op.create_index(
        "ix_model_configurations_tenant_purpose_enabled",
        "model_configurations",
        ["tenant_id", "purpose", "enabled"],
    )
    op.create_index(
        "ix_model_configurations_provider_connection_id",
        "model_configurations",
        ["provider_connection_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_model_configurations_provider_connection_id",
        table_name="model_configurations",
    )
    op.drop_index(
        "ix_model_configurations_tenant_purpose_enabled",
        table_name="model_configurations",
    )
    op.drop_table("model_configurations")
    op.drop_index(
        "ix_provider_connections_tenant_provider_status",
        table_name="provider_connections",
    )
    op.drop_table("provider_connections")
