"""Trusted tenant membership and effective-capability resolution."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tenancy.errors import TenantMembershipAccessError
from app.modules.tenancy.models import Membership
from app.modules.tenancy.repository import (
    add_invited_membership,
    add_membership_role,
    find_membership,
    find_membership_for_update,
    list_effective_permission_keys,
    list_membership_role_ids,
)
from app.modules.tenancy.schemas import ResolvedTenantMembership


async def resolve_tenant_membership(
    session: AsyncSession,
    *,
    user_id: UUID,
    tenant_id: UUID,
) -> ResolvedTenantMembership:
    """Resolve one trusted user/tenant pair or fail closed."""

    membership = await find_membership(session, tenant_id=tenant_id, user_id=user_id)
    if membership is None or membership.status != "active":
        raise TenantMembershipAccessError

    permissions = await list_effective_permission_keys(
        session,
        membership_id=membership.id,
        tenant_id=tenant_id,
    )
    return ResolvedTenantMembership(
        membership_id=membership.id,
        tenant_id=membership.tenant_id,
        user_id=membership.user_id,
        status=membership.status,
        permissions=permissions,
    )


async def activate_membership_from_invitation(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
    invitation_id: UUID,
    role_ids: tuple[UUID, ...],
    now: datetime,
) -> Membership:
    """Create or activate one membership and add only missing invitation roles.

    The caller owns the surrounding transaction. This function deliberately does not
    commit so membership, role mappings, and the invitation accepted transition can
    succeed or roll back together.
    """

    membership = await find_membership_for_update(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    if membership is None:
        membership = add_invited_membership(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            invitation_id=invitation_id,
        )
        await session.flush()
    elif membership.status == "suspended":
        membership.status = "active"
        membership.updated_at = now
        await session.flush()
    elif membership.status != "active":
        raise TenantMembershipAccessError

    existing_role_ids = await list_membership_role_ids(
        session,
        membership_id=membership.id,
    )
    for role_id in role_ids:
        if role_id not in existing_role_ids:
            add_membership_role(
                session,
                membership_id=membership.id,
                role_id=role_id,
            )
    await session.flush()
    return membership
