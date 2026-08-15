"""Seed provider-management capability for existing V1 Owner/Admin roles.

Revision ID: 20260815_0006
Revises: 20260815_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260815_0006"
down_revision: str | Sequence[str] | None = "20260815_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION = "ai.providers.manage"


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO role_permissions (role_id, permission_key)
            SELECT id, :permission
            FROM roles
            WHERE tenant_id IS NULL
              AND is_system = true
              AND key IN ('owner', 'admin')
            """
        ),
        {"permission": PERMISSION},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            DELETE FROM role_permissions
            WHERE permission_key = :permission
              AND role_id IN (
                SELECT id FROM roles
                WHERE tenant_id IS NULL
                  AND is_system = true
                  AND key IN ('owner', 'admin')
              )
            """
        ),
        {"permission": PERMISSION},
    )
