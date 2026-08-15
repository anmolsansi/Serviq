"""Tenant member listing, authorization, and atomic role/status updates."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.members.errors import (
    LastActiveOwnerConflictError,
    MembershipAccessNotFoundError,
    MembershipForbiddenError,
    MembershipRoleInvalidError,
)
from app.modules.members.repository import (
    count_active_owners,
    find_assignable_roles,
    find_tenant_membership,
    find_workforce_user,
    list_membership_roles,
    list_tenant_memberships,
    lock_organization,
    replace_membership_roles,
)
from app.modules.members.schemas import (
    MemberRoleView,
    MemberUpdateRequest,
    MemberView,
)
from app.modules.tenancy.errors import TenantMembershipAccessError
from app.modules.tenancy.models import Membership, Role
from app.modules.tenancy.service import resolve_tenant_membership
from app.modules.workforce.models import User

MEMBER_MANAGE_PERMISSION = "organization.members.manage"


async def list_members(
    session: AsyncSession,
    *,
    user_id: UUID,
    organization_id: UUID,
    limit: int,
    offset: int,
) -> tuple[MemberView, ...]:
    await _require_manage_permission(
        session,
        user_id=user_id,
        organization_id=organization_id,
    )
    memberships = await list_tenant_memberships(
        session,
        tenant_id=organization_id,
        limit=limit,
        offset=offset,
    )
    return tuple(
        [
            await _membership_view(session, membership=membership)
            for membership in memberships
        ]
    )


async def update_member(
    session: AsyncSession,
    *,
    user_id: UUID,
    organization_id: UUID,
    membership_id: UUID,
    request: MemberUpdateRequest,
) -> MemberView:
    """Apply role replacement/status change as one serialized tenant transaction."""

    async with session.begin():
        organization = await lock_organization(session, tenant_id=organization_id)
        if organization is None:
            raise MembershipAccessNotFoundError

        await _require_manage_permission(
            session,
            user_id=user_id,
            organization_id=organization_id,
        )
        target = await find_tenant_membership(
            session,
            tenant_id=organization_id,
            membership_id=membership_id,
        )
        if target is None:
            raise MembershipAccessNotFoundError

        current_roles = await list_membership_roles(
            session,
            membership_id=target.id,
        )
        next_roles = current_roles
        if request.role_ids is not None:
            assignable = await find_assignable_roles(
                session,
                tenant_id=organization_id,
                role_ids=request.role_ids,
            )
            if {role.id for role in assignable} != set(request.role_ids):
                raise MembershipRoleInvalidError
            next_roles = tuple(assignable)

        next_status = request.status or target.status
        removes_active_owner = (
            target.status == "active"
            and _contains_owner(current_roles)
            and (next_status != "active" or not _contains_owner(next_roles))
        )
        if removes_active_owner:
            active_owner_count = await count_active_owners(
                session,
                tenant_id=organization_id,
            )
            if active_owner_count <= 1:
                raise LastActiveOwnerConflictError

        if request.role_ids is not None:
            await replace_membership_roles(
                session,
                membership_id=target.id,
                role_ids=tuple(role.id for role in next_roles),
            )
        if request.status is not None and request.status != target.status:
            target.status = request.status
            target.updated_at = datetime.now(UTC)
            await session.flush()

        return await _membership_view(session, membership=target)


async def _require_manage_permission(
    session: AsyncSession,
    *,
    user_id: UUID,
    organization_id: UUID,
) -> None:
    try:
        caller = await resolve_tenant_membership(
            session,
            user_id=user_id,
            tenant_id=organization_id,
        )
    except TenantMembershipAccessError:
        raise MembershipAccessNotFoundError from None
    if MEMBER_MANAGE_PERMISSION not in caller.permissions:
        raise MembershipForbiddenError


async def _membership_view(
    session: AsyncSession,
    *,
    membership: Membership,
) -> MemberView:
    user = await find_workforce_user(session, user_id=membership.user_id)
    if user is None:
        raise MembershipAccessNotFoundError
    roles = await list_membership_roles(session, membership_id=membership.id)
    return _to_view(membership=membership, user=user, roles=roles)


def _to_view(
    *,
    membership: Membership,
    user: User,
    roles: tuple[Role, ...],
) -> MemberView:
    return MemberView(
        membershipId=membership.id,
        userId=user.id,
        email=user.email,
        displayName=user.display_name,
        status=membership.status,
        roles=tuple(
            MemberRoleView(id=role.id, key=role.key, displayName=role.display_name)
            for role in roles
        ),
    )


def _contains_owner(roles: tuple[Role, ...]) -> bool:
    return any(
        role.tenant_id is None and role.is_system and role.key == "owner"
        for role in roles
    )
