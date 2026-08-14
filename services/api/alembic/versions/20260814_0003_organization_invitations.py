"""Create organization invitation persistence and complete CCR-004.

Revision ID: 20260814_0003
Revises: 20260814_0002

The schema stores only a globally unique token hash. No plaintext invitation
token column exists. After organization_invitations exists, this revision also
completes CCR-004 by adding the deferred membership invitation foreign key.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260814_0003"
down_revision: str | Sequence[str] | None = "20260814_0002"
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
        "organization_invitations",
        _id_column(),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("email_normalized", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("invited_by_user_id", UUID, nullable=False),
        sa.Column("accepted_by_user_id", UUID, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.CheckConstraint(
            "char_length(email_normalized) BETWEEN 3 AND 320",
            name="ck_organization_invitations_email_length",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')",
            name="ck_organization_invitations_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_organization_invitations_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"],
            ["users.id"],
            name="fk_organization_invitations_invited_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["accepted_by_user_id"],
            ["users.id"],
            name="fk_organization_invitations_accepted_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "token_hash",
            name="uq_organization_invitations_token_hash",
        ),
    )
    op.create_index(
        "ix_organization_invitations_tenant_status_expires_at",
        "organization_invitations",
        ["tenant_id", "status", "expires_at"],
    )
    op.create_index(
        "ix_organization_invitations_tenant_email_normalized",
        "organization_invitations",
        ["tenant_id", "email_normalized"],
    )
    op.create_index(
        "ix_organization_invitations_invited_by_user_id",
        "organization_invitations",
        ["invited_by_user_id"],
    )
    op.create_index(
        "ix_organization_invitations_accepted_by_user_id",
        "organization_invitations",
        ["accepted_by_user_id"],
    )
    op.create_index(
        "uq_organization_invitations_pending_tenant_email",
        "organization_invitations",
        ["tenant_id", "email_normalized"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    op.create_table(
        "organization_invitation_roles",
        _id_column(),
        sa.Column("invitation_id", UUID, nullable=False),
        sa.Column("role_id", UUID, nullable=False),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(
            ["invitation_id"],
            ["organization_invitations.id"],
            name=(
                "fk_organization_invitation_roles_invitation_id_organization_invitations"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name="fk_organization_invitation_roles_role_id_roles",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "invitation_id",
            "role_id",
            name="uq_organization_invitation_roles_invitation_role",
        ),
    )
    op.create_index(
        "ix_organization_invitation_roles_invitation_id",
        "organization_invitation_roles",
        ["invitation_id"],
    )
    op.create_index(
        "ix_organization_invitation_roles_role_id",
        "organization_invitation_roles",
        ["role_id"],
    )

    op.create_foreign_key(
        "fk_memberships_created_by_invitation_id_organization_invitations",
        "memberships",
        "organization_invitations",
        ["created_by_invitation_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_memberships_created_by_invitation_id_organization_invitations",
        "memberships",
        type_="foreignkey",
    )
    op.drop_table("organization_invitation_roles")
    op.drop_table("organization_invitations")
