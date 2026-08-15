"""Tenant-scoped persistence for workforce member management."""

from uuid import UUID

from sqlalchemy import and_, delete, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.modules.tenancy.models import Membership, MembershipRole, Role
from app.modules.workforce.models import User

ASSIGNABLE_GLOBAL_ROLE_KEYS = frozenset({"owner", "admin"})
OWNER_ROLE_KEY = "owner"


async def list_tenant_memberships(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    limit: int,
    offset: int,
) -> tuple[Membership, ...]:
    result = await session.execute(
        select(Membership)
        .where(Membership.tenant_id == tenant_id)
        .order_by(Membership.created_at, Membership.id)
        .limit(limit)
        .offset(offset)
    )
    return tuple(result.scalars().all())


async def find_tenant_membership(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    membership_id: UUID,
) -> Membership | None:
    result = await session.execute(
        select(Membership).where(
            Membership.id == membership_id,
            Membership.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def find_workforce_user(
    session: AsyncSession,
    *,
    user_id: UUID,
) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def list_membership_roles(
    session: AsyncSession,
    *,
    membership_id: UUID,
) -> tuple[Role, ...]:
    result = await session.execute(
        select(Role)
        .join(MembershipRole, MembershipRole.role_id == Role.id)
        .where(MembershipRole.membership_id == membership_id)
        .order_by(Role.key, Role.id)
    )
    return tuple(result.scalars().all())


async def find_assignable_roles(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    role_ids: list[UUID],
) -> tuple[Role, ...]:
    """Allow tenant roles plus the frozen global owner/admin workforce roles only."""

    approved_global = and_(
        Role.tenant_id.is_(None),
        Role.is_system.is_(True),
        Role.key.in_(ASSIGNABLE_GLOBAL_ROLE_KEYS),
    )
    result = await session.execute(
        select(Role).where(
            Role.id.in_(role_ids),
            or_(Role.tenant_id == tenant_id, approved_global),
        )
    )
    return tuple(result.scalars().all())


async def lock_organization(
    session: AsyncSession,
    *,
    tenant_id: UUID,
) -> Organization | None:
    """Serialize member mutations for one tenant, including last-owner decisions."""

    result = await session.execute(
        select(Organization)
        .where(Organization.id == tenant_id)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def count_active_owners(
    session: AsyncSession,
    *,
    tenant_id: UUID,
) -> int:
    result = await session.execute(
        select(func.count(distinct(Membership.id)))
        .join(MembershipRole, MembershipRole.membership_id == Membership.id)
        .join(Role, Role.id == MembershipRole.role_id)
        .where(
            Membership.tenant_id == tenant_id,
            Membership.status == "active",
            Role.tenant_id.is_(None),
            Role.is_system.is_(True),
            Role.key == OWNER_ROLE_KEY,
        )
    )
    return int(result.scalar_one())


async def replace_membership_roles(
    session: AsyncSession,
    *,
    membership_id: UUID,
    role_ids: tuple[UUID, ...],
) -> None:
    await session.execute(
        delete(MembershipRole).where(MembershipRole.membership_id == membership_id)
    )
    for role_id in role_ids:
        session.add(MembershipRole(membership_id=membership_id, role_id=role_id))
    await session.flush()
