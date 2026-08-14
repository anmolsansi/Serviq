"""Create tenant, workforce, and RBAC tables.

Revision ID: 20260814_0002
Revises: 20260814_0001

CCR-004 intentionally defers the memberships.created_by_invitation_id foreign
key until organization_invitations is created by OPE-278. The nullable column
is created here so the final schema shape stays frozen.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260814_0002"
down_revision: str | Sequence[str] | None = "20260814_0001"
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
        "tenants",
        _id_column(),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "default_locale",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'en'"),
        ),
        _created_at_column(),
        _updated_at_column(),
        sa.CheckConstraint(
            "char_length(slug) BETWEEN 3 AND 63",
            name="ck_tenants_slug_length",
        ),
        sa.CheckConstraint(
            "char_length(display_name) BETWEEN 1 AND 120",
            name="ck_tenants_display_name_length",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'deleted')",
            name="ck_tenants_status",
        ),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )
    op.create_index("ix_tenants_status", "tenants", ["status"])

    op.create_table(
        "users",
        _id_column(),
        sa.Column("oidc_issuer", sa.Text(), nullable=False),
        sa.Column("oidc_subject", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        _created_at_column(),
        _updated_at_column(),
        sa.CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_users_status",
        ),
        sa.UniqueConstraint(
            "oidc_issuer",
            "oidc_subject",
            name="uq_users_oidc_identity",
        ),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "memberships",
        _id_column(),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_by_invitation_id", UUID, nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.CheckConstraint(
            "status IN ('active', 'suspended')",
            name="ck_memberships_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_memberships_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_memberships_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            name="uq_memberships_tenant_user",
        ),
    )
    op.create_index(
        "ix_memberships_tenant_id_status",
        "memberships",
        ["tenant_id", "status"],
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_index(
        "ix_memberships_created_by_invitation_id",
        "memberships",
        ["created_by_invitation_id"],
    )

    op.create_table(
        "roles",
        _id_column(),
        sa.Column("tenant_id", UUID, nullable=True),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column(
            "is_system",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        _created_at_column(),
        _updated_at_column(),
        sa.CheckConstraint(
            "char_length(key) BETWEEN 2 AND 64",
            name="ck_roles_key_length",
        ),
        sa.CheckConstraint(
            "char_length(display_name) BETWEEN 1 AND 80",
            name="ck_roles_display_name_length",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_roles_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "key",
            name="uq_roles_tenant_key",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index("ix_roles_tenant_id", "roles", ["tenant_id"])

    op.create_table(
        "role_permissions",
        _id_column(),
        sa.Column("role_id", UUID, nullable=False),
        sa.Column("permission_key", sa.Text(), nullable=False),
        _created_at_column(),
        _updated_at_column(),
        sa.CheckConstraint(
            "char_length(permission_key) BETWEEN 2 AND 120",
            name="ck_role_permissions_permission_key_length",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name="fk_role_permissions_role_id_roles",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "role_id",
            "permission_key",
            name="uq_role_permissions_role_permission",
        ),
    )
    op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"])

    op.create_table(
        "membership_roles",
        _id_column(),
        sa.Column("membership_id", UUID, nullable=False),
        sa.Column("role_id", UUID, nullable=False),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(
            ["membership_id"],
            ["memberships.id"],
            name="fk_membership_roles_membership_id_memberships",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name="fk_membership_roles_role_id_roles",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "membership_id",
            "role_id",
            name="uq_membership_roles_membership_role",
        ),
    )
    op.create_index(
        "ix_membership_roles_membership_id",
        "membership_roles",
        ["membership_id"],
    )
    op.create_index("ix_membership_roles_role_id", "membership_roles", ["role_id"])


def downgrade() -> None:
    op.drop_table("membership_roles")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("memberships")
    op.drop_table("users")
    op.drop_table("tenants")
