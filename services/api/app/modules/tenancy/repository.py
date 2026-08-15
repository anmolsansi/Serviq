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


async def find_membership_for_update(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
) -> Membership | None:
    """Lock the exact membership row when invitation acceptance may activate it."""

    result = await session.execute(
        select(Membership)
        .where(
            Membership.tenant_id == tenant_id,
            Membership.user_id == user_id,
        )
        .with_for_update()
    )
    return result.scalar_one_or_none()


def add_invited_membership(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
    invitation_id: UUID,
) -> Membership:
    """Stage a new active membership created by one accepted invitation."""

    membership = Membership(
        tenant_id=tenant_id,
        user_id=user_id,
        status="active",
        created_by_invitation_id=invitation_id,
    )
    session.add(membership)
    return membership


async def list_membership_role_ids(
    session: AsyncSession,
    *,
    membership_id: UUID,
) -> frozenset[UUID]:
    result = await session.execute(
        select(MembershipRole.role_id).where(
            MembershipRole.membership_id == membership_id
        )
    )
    return frozenset(result.scalars().all())


def add_membership_role(
    session: AsyncSession,
    *,
    membership_id: UUID,
    role_id: UUID,
) -> MembershipRole:
    mapping = MembershipRole(membership_id=membership_id, role_id=role_id)
    session.add(mapping)
    return mapping


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
