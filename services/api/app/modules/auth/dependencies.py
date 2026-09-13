"""Dependencies for composing the trusted RequestContext."""

from typing import Annotated
from uuid import UUID

from fastapi import Cookie, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import VerifiedWorkforceIdentity
from app.core.database import get_database_session
from app.core.errors import AuthenticationError, MissingTenantContextError
from app.core.session import ValkeySessionStore, get_session_store
from app.modules.tenancy.schemas import ResolvedTenantMembership
from app.modules.tenancy.service import resolve_tenant_membership


async def require_workforce_session(
    request: Request,
    serviq_session: Annotated[str | None, Cookie()] = None,
    session_store: ValkeySessionStore = Depends(get_session_store),  # noqa: B008
) -> UUID:
    """Require a valid workforce session and return the user ID.

    Populates `request.state.serviq_user_id`.
    """
    if not serviq_session:
        raise AuthenticationError

    session_data = await session_store.get_session(serviq_session)
    if not session_data:
        raise AuthenticationError

    request.state.serviq_user_id = session_data.user_id
    request.state.serviq_workforce_identity = VerifiedWorkforceIdentity(
        subject=session_data.oidc_subject,
        issuer=session_data.oidc_issuer,
        email=session_data.email,
        email_verified=session_data.email_verified,
    )
    return session_data.user_id


async def require_tenant_context(
    request: Request,
    user_id: UUID = Depends(require_workforce_session),  # noqa: B008
    x_serviq_tenant_id: Annotated[UUID | None, Header()] = None,
    db: AsyncSession = Depends(get_database_session),  # noqa: B008
) -> ResolvedTenantMembership:
    """Require an explicit tenant context header and verify membership.

    Populates `request.state.serviq_tenant_id`.
    """
    if not x_serviq_tenant_id:
        raise MissingTenantContextError

    # resolve_tenant_membership checks existence and active status.
    # It raises TenantMembershipAccessError (a subclass of AuthenticationError) if denied.
    membership = await resolve_tenant_membership(
        db,
        user_id=user_id,
        tenant_id=x_serviq_tenant_id,
    )

    request.state.serviq_tenant_id = membership.tenant_id
    # We could also stash the full membership on request.state if needed,
    # but the architectural contract only asks for serviq_tenant_id.

    return membership
