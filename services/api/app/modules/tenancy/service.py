"""Trusted tenant membership and effective-capability resolution."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tenancy.errors import TenantMembershipAccessError
from app.modules.tenancy.repository import find_membership, list_effective_permission_keys
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
