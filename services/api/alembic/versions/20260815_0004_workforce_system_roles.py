"""Seed V1 workforce Owner/Admin system roles.

Revision ID: 20260815_0004
Revises: 20260814_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260815_0004"
down_revision: str | None = "20260814_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO roles (tenant_id, key, display_name, is_system)
            VALUES
                (NULL, 'owner', 'Owner', true),
                (NULL, 'admin', 'Admin', true)
            """
        )
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO role_permissions (role_id, permission_key)
            SELECT id, 'organization.settings.write'
            FROM roles
            WHERE tenant_id IS NULL AND is_system = true AND key IN ('owner', 'admin')
            UNION ALL
            SELECT id, 'organization.members.manage'
            FROM roles
            WHERE tenant_id IS NULL AND is_system = true AND key IN ('owner', 'admin')
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM roles
            WHERE tenant_id IS NULL
              AND is_system = true
              AND key IN ('owner', 'admin')
            """
        )
    )
