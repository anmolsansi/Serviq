"""Membership-scoped organization persistence operations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.modules.tenancy.models import Membership, MembershipRole, Role


async def list_active_organizations_for_user(
    session: AsyncSession,
    *,
    user_id: UUID,
) -> tuple[Organization, ...]:
    result = await session.execute(
        select(Organization)
        .join(Membership, Membership.tenant_id == Organization.id)
        .where(
            Membership.user_id == user_id,
            Membership.status == "active",
        )
        .order_by(Organization.created_at, Organization.id)
    )
    return tuple(result.scalars().all())


async def find_global_system_role(
    session: AsyncSession,
    *,
    key: str,
) -> Role | None:
    result = await session.execute(
        select(Role).where(
            Role.tenant_id.is_(None),
            Role.is_system.is_(True),
            Role.key == key,
        )
    )
    return result.scalar_one_or_none()


def add_organization(
    session: AsyncSession,
    *,
    slug: str,
    display_name: str,
) -> Organization:
    organization = Organization(
        slug=slug,
        display_name=display_name,
        status="active",
        default_locale="en",
    )
    session.add(organization)
    return organization


def add_active_membership(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
) -> Membership:
    membership = Membership(
        tenant_id=tenant_id,
        user_id=user_id,
        status="active",
    )
    session.add(membership)
    return membership


def add_membership_role(
    session: AsyncSession,
    *,
    membership_id: UUID,
    role_id: UUID,
) -> MembershipRole:
    mapping = MembershipRole(membership_id=membership_id, role_id=role_id)
    session.add(mapping)
    return mapping
