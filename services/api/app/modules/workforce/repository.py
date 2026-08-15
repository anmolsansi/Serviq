"""Tenant-independent persistence operations for workforce user identities."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.workforce.models import User


async def find_user_by_oidc_identity(
    session: AsyncSession,
    *,
    issuer: str,
    subject: str,
) -> User | None:
    """Fetch exactly one internal user by the frozen external identity key."""

    statement = select(User).where(
        User.oidc_issuer == issuer,
        User.oidc_subject == subject,
    )
    result = await session.execute(statement)
    return result.scalar_one_or_none()


def add_user(
    session: AsyncSession,
    *,
    issuer: str,
    subject: str,
    email: str,
    display_name: str,
) -> User:
    """Stage a new active user row; the service owns flush/transaction behavior."""

    user = User(
        oidc_issuer=issuer,
        oidc_subject=subject,
        email=email,
        display_name=display_name,
        status="active",
    )
    session.add(user)
    return user
