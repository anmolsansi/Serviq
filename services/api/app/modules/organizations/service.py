"""Organization business rules and transaction ownership."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.errors import (
    OrganizationNotFoundError,
    OrganizationSettingsForbiddenError,
    OrganizationSlugConflictError,
    OwnerRoleUnavailableError,
)
from app.modules.organizations.models import Organization
from app.modules.organizations.repository import (
    add_active_membership,
    add_membership_role,
    add_organization,
    find_global_system_role,
    find_organization_for_active_member,
    list_active_organizations_for_user,
)
from app.modules.organizations.schemas import (
    OrganizationCreateRequest,
    OrganizationUpdateRequest,
    OrganizationView,
)
from app.modules.tenancy.service import resolve_tenant_membership

OWNER_ROLE_KEY = "owner"
ORGANIZATION_SETTINGS_PERMISSION = "organization.settings.write"


async def list_organizations(
    session: AsyncSession,
    *,
    user_id: UUID,
) -> tuple[OrganizationView, ...]:
    organizations = await list_active_organizations_for_user(session, user_id=user_id)
    return tuple(_to_view(item) for item in organizations)


async def get_organization(
    session: AsyncSession,
    *,
    user_id: UUID,
    organization_id: UUID,
) -> OrganizationView:
    organization = await find_organization_for_active_member(
        session,
        organization_id=organization_id,
        user_id=user_id,
    )
    if organization is None:
        raise OrganizationNotFoundError
    return _to_view(organization)


async def create_organization(
    session: AsyncSession,
    *,
    user_id: UUID,
    request: OrganizationCreateRequest,
) -> OrganizationView:
    """Atomically create tenant, active creator membership, and Owner mapping."""

    async with session.begin():
        owner_role = await find_global_system_role(session, key=OWNER_ROLE_KEY)
        if owner_role is None:
            raise OwnerRoleUnavailableError

        organization = add_organization(
            session,
            slug=request.slug,
            display_name=request.display_name,
        )
        try:
            await session.flush()
        except IntegrityError:
            raise OrganizationSlugConflictError from None

        membership = add_active_membership(
            session,
            tenant_id=organization.id,
            user_id=user_id,
        )
        await session.flush()

        add_membership_role(
            session,
            membership_id=membership.id,
            role_id=owner_role.id,
        )
        await session.flush()
        return _to_view(organization)


async def update_organization(
    session: AsyncSession,
    *,
    user_id: UUID,
    organization_id: UUID,
    request: OrganizationUpdateRequest,
) -> OrganizationView:
    """Update only safe organization settings after membership and capability checks."""

    async with session.begin():
        organization = await find_organization_for_active_member(
            session,
            organization_id=organization_id,
            user_id=user_id,
        )
        if organization is None:
            raise OrganizationNotFoundError

        membership = await resolve_tenant_membership(
            session,
            user_id=user_id,
            tenant_id=organization_id,
        )
        if ORGANIZATION_SETTINGS_PERMISSION not in membership.permissions:
            raise OrganizationSettingsForbiddenError

        if request.display_name is not None:
            organization.display_name = request.display_name
        if request.default_locale is not None:
            organization.default_locale = request.default_locale
        organization.updated_at = datetime.now(UTC)
        await session.flush()
        return _to_view(organization)


def _to_view(organization: Organization) -> OrganizationView:
    return OrganizationView(
        id=organization.id,
        slug=organization.slug,
        displayName=organization.display_name,
        status=organization.status,
        defaultLocale=organization.default_locale,
    )
