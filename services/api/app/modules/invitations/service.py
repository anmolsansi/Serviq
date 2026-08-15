"""Invitation lifecycle, authorization, and secret-handling business rules."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.invitations.errors import (
    InvitationAccessNotFoundError,
    InvitationConflictError,
    InvitationForbiddenError,
    InvitationLifecycleConflictError,
    InvitationRoleInvalidError,
)
from app.modules.invitations.models import OrganizationInvitation
from app.modules.invitations.repository import (
    add_invitation,
    add_invitation_role,
    find_assignable_roles,
    find_tenant_invitation,
    list_invitation_roles,
    list_tenant_invitations,
)
from app.modules.invitations.schemas import (
    InvitationCreateRequest,
    InvitationCreateView,
    InvitationRoleView,
    InvitationView,
)
from app.modules.invitations.security import (
    build_invitation_url,
    generate_invitation_token,
    hash_invitation_token,
)
from app.modules.tenancy.errors import TenantMembershipAccessError
from app.modules.tenancy.models import Role
from app.modules.tenancy.service import resolve_tenant_membership

INVITATION_MANAGE_PERMISSION = "organization.members.manage"
INVITATION_LIFETIME = timedelta(days=7)
Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


async def create_invitation(
    session: AsyncSession,
    *,
    user_id: UUID,
    organization_id: UUID,
    request: InvitationCreateRequest,
    public_base_url: str,
    clock: Clock = utc_now,
) -> InvitationCreateView:
    """Create one invitation while keeping plaintext bearer material out of storage."""

    async with session.begin():
        await _require_manage_permission(
            session,
            user_id=user_id,
            organization_id=organization_id,
        )
        roles = await find_assignable_roles(
            session,
            tenant_id=organization_id,
            role_ids=request.role_ids,
        )
        if {role.id for role in roles} != set(request.role_ids):
            raise InvitationRoleInvalidError

        plaintext_token = generate_invitation_token()
        token_hash = hash_invitation_token(plaintext_token)
        now = clock()

        invitation = add_invitation(
            session,
            tenant_id=organization_id,
            email_normalized=request.email,
            token_hash=token_hash,
            invited_by_user_id=user_id,
            expires_at=now + INVITATION_LIFETIME,
        )
        try:
            await session.flush()
        except IntegrityError:
            raise InvitationConflictError from None

        for role in roles:
            add_invitation_role(
                session,
                invitation_id=invitation.id,
                role_id=role.id,
            )
        await session.flush()

        safe_view = _to_view(invitation, roles)

    return InvitationCreateView(
        **safe_view.model_dump(),
        inviteUrl=build_invitation_url(public_base_url, plaintext_token),
    )


async def list_invitations(
    session: AsyncSession,
    *,
    user_id: UUID,
    organization_id: UUID,
) -> tuple[InvitationView, ...]:
    await _require_manage_permission(
        session,
        user_id=user_id,
        organization_id=organization_id,
    )
    invitations = await list_tenant_invitations(session, tenant_id=organization_id)
    views: list[InvitationView] = []
    for invitation in invitations:
        roles = await list_invitation_roles(session, invitation_id=invitation.id)
        views.append(_to_view(invitation, roles))
    return tuple(views)


async def revoke_invitation(
    session: AsyncSession,
    *,
    user_id: UUID,
    organization_id: UUID,
    invitation_id: UUID,
    clock: Clock = utc_now,
) -> InvitationView:
    now = clock()
    async with session.begin():
        await _require_manage_permission(
            session,
            user_id=user_id,
            organization_id=organization_id,
        )
        invitation = await find_tenant_invitation(
            session,
            tenant_id=organization_id,
            invitation_id=invitation_id,
        )
        if invitation is None:
            raise InvitationAccessNotFoundError
        if invitation.status != "pending" or invitation.expires_at <= now:
            raise InvitationLifecycleConflictError

        invitation.status = "revoked"
        invitation.revoked_at = now
        invitation.updated_at = now
        await session.flush()
        roles = await list_invitation_roles(session, invitation_id=invitation.id)
        return _to_view(invitation, roles)


async def _require_manage_permission(
    session: AsyncSession,
    *,
    user_id: UUID,
    organization_id: UUID,
) -> None:
    try:
        membership = await resolve_tenant_membership(
            session,
            user_id=user_id,
            tenant_id=organization_id,
        )
    except TenantMembershipAccessError:
        raise InvitationAccessNotFoundError from None

    if INVITATION_MANAGE_PERMISSION not in membership.permissions:
        raise InvitationForbiddenError


def _to_view(
    invitation: OrganizationInvitation,
    roles: tuple[Role, ...],
) -> InvitationView:
    return InvitationView(
        id=invitation.id,
        email=invitation.email_normalized,
        status=invitation.status,
        expiresAt=invitation.expires_at,
        roles=tuple(
            InvitationRoleView(id=role.id, key=role.key, displayName=role.display_name)
            for role in roles
        ),
        invitedByUserId=invitation.invited_by_user_id,
        acceptedByUserId=invitation.accepted_by_user_id,
        acceptedAt=invitation.accepted_at,
        revokedAt=invitation.revoked_at,
        createdAt=invitation.created_at,
        updatedAt=invitation.updated_at,
    )
