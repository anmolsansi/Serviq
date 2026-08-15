"""Tenant-scoped invitation persistence operations."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.invitations.models import OrganizationInvitation, OrganizationInvitationRole
from app.modules.tenancy.models import Role

ASSIGNABLE_GLOBAL_ROLE_KEYS = frozenset({"owner", "admin"})


async def find_assignable_roles(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    role_ids: list[UUID],
) -> tuple[Role, ...]:
    """Resolve only tenant-owned or explicitly approved global workforce roles."""

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


def add_invitation(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    email_normalized: str,
    token_hash: str,
    invited_by_user_id: UUID,
    expires_at: datetime,
) -> OrganizationInvitation:
    invitation = OrganizationInvitation(
        tenant_id=tenant_id,
        email_normalized=email_normalized,
        token_hash=token_hash,
        status="pending",
        invited_by_user_id=invited_by_user_id,
        expires_at=expires_at,
    )
    session.add(invitation)
    return invitation


def add_invitation_role(
    session: AsyncSession,
    *,
    invitation_id: UUID,
    role_id: UUID,
) -> OrganizationInvitationRole:
    mapping = OrganizationInvitationRole(invitation_id=invitation_id, role_id=role_id)
    session.add(mapping)
    return mapping


async def list_tenant_invitations(
    session: AsyncSession,
    *,
    tenant_id: UUID,
) -> tuple[OrganizationInvitation, ...]:
    result = await session.execute(
        select(OrganizationInvitation)
        .where(OrganizationInvitation.tenant_id == tenant_id)
        .order_by(
            OrganizationInvitation.created_at.desc(),
            OrganizationInvitation.id.desc(),
        )
    )
    return tuple(result.scalars().all())


async def list_invitation_roles(
    session: AsyncSession,
    *,
    invitation_id: UUID,
) -> tuple[Role, ...]:
    result = await session.execute(
        select(Role)
        .join(OrganizationInvitationRole, OrganizationInvitationRole.role_id == Role.id)
        .where(OrganizationInvitationRole.invitation_id == invitation_id)
        .order_by(Role.key, Role.id)
    )
    return tuple(result.scalars().all())


async def find_tenant_invitation(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    invitation_id: UUID,
) -> OrganizationInvitation | None:
    result = await session.execute(
        select(OrganizationInvitation).where(
            OrganizationInvitation.id == invitation_id,
            OrganizationInvitation.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()
