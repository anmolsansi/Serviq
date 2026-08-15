"""Tenant-scoped membership and RBAC persistence operations."""

from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tenancy.models import Membership, MembershipRole, Role, RolePermission


async def find_membership(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
) -> Membership | None:
    """Load only the exact trusted tenant/user membership pair."""

    result = await session.execute(
        select(Membership).where(
            Membership.tenant_id == tenant_id,
            Membership.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def list_effective_permission_keys(
    session: AsyncSession,
    *,
    membership_id: UUID,
    tenant_id: UUID,
) -> tuple[str, ...]:
    """Return permissions only from target-tenant or approved global system roles."""

    approved_role = or_(
        Role.tenant_id == tenant_id,
        and_(Role.tenant_id.is_(None), Role.is_system.is_(True)),
    )
    statement = (
        select(RolePermission.permission_key)
        .join(MembershipRole, MembershipRole.role_id == RolePermission.role_id)
        .join(Role, Role.id == MembershipRole.role_id)
        .where(
            MembershipRole.membership_id == membership_id,
            approved_role,
        )
    )
    result = await session.execute(statement)
    return tuple(sorted(set(result.scalars().all())))
