"""Business rules for mapping verified OIDC identity to one internal user."""

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import VerifiedWorkforceIdentity
from app.modules.workforce.errors import (
    DisabledWorkforceUserError,
    WorkforceIdentityProfileError,
)
from app.modules.workforce.models import User
from app.modules.workforce.repository import add_user, find_user_by_oidc_identity
from app.modules.workforce.schemas import InternalWorkforceUser


async def upsert_verified_workforce_user(
    session: AsyncSession,
    identity: VerifiedWorkforceIdentity,
) -> InternalWorkforceUser:
    """Resolve one verified external identity to one stable internal user.

    The service owns the transaction. A nested savepoint contains the only expected
    concurrent first-login conflict so the losing caller can safely reload the row
    that won the database unique constraint.
    """

    email = identity.email
    if email is None:
        raise WorkforceIdentityProfileError

    display_name = identity.display_name or email

    async with session.begin():
        existing = await find_user_by_oidc_identity(
            session,
            issuer=identity.issuer,
            subject=identity.subject,
        )
        if existing is not None:
            await _sync_active_user(
                session,
                existing,
                email=email,
                display_name=identity.display_name,
            )
            return _to_internal_user(existing)

        try:
            async with session.begin_nested():
                created = add_user(
                    session,
                    issuer=identity.issuer,
                    subject=identity.subject,
                    email=email,
                    display_name=display_name,
                )
                await session.flush()
        except IntegrityError:
            winner = await find_user_by_oidc_identity(
                session,
                issuer=identity.issuer,
                subject=identity.subject,
            )
            if winner is None:
                raise
            await _sync_active_user(
                session,
                winner,
                email=email,
                display_name=identity.display_name,
            )
            return _to_internal_user(winner)

        return _to_internal_user(created)


async def _sync_active_user(
    session: AsyncSession,
    user: User,
    *,
    email: str,
    display_name: str | None,
) -> None:
    if user.status != "active":
        raise DisabledWorkforceUserError

    changed = False
    if user.email != email:
        user.email = email
        changed = True
    if display_name is not None and user.display_name != display_name:
        user.display_name = display_name
        changed = True

    if changed:
        user.updated_at = datetime.now(UTC)
        await session.flush()


def _to_internal_user(user: User) -> InternalWorkforceUser:
    return InternalWorkforceUser(
        id=user.id,
        oidc_issuer=user.oidc_issuer,
        oidc_subject=user.oidc_subject,
        email=user.email,
        display_name=user.display_name,
        status=user.status,
    )
