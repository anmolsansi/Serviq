"""Organization list/create business rules and transaction ownership."""

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.errors import (
    OrganizationSlugConflictError,
    OwnerRoleUnavailableError,
)
from app.modules.organizations.models import Organization
from app.modules.organizations.repository import (
    add_active_membership,
    add_membership_role,
    add_organization,
    find_global_system_role,
    list_active_organizations_for_user,
)
from app.modules.organizations.schemas import OrganizationCreateRequest, OrganizationView

OWNER_ROLE_KEY = "owner"


async def list_organizations(
    session: AsyncSession,
    *,
    user_id: UUID,
) -> tuple[OrganizationView, ...]:
    organizations = await list_active_organizations_for_user(session, user_id=user_id)
    return tuple(_to_view(item) for item in organizations)


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


def _to_view(organization: Organization) -> OrganizationView:
    return OrganizationView(
        id=organization.id,
        slug=organization.slug,
        displayName=organization.display_name,
        status=organization.status,
        defaultLocale=organization.default_locale,
    )
