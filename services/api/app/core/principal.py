"""Server-owned workforce principal handoff for protected API routes."""

from uuid import UUID

from fastapi import Request

from app.core.auth import VerifiedWorkforceIdentity
from app.core.errors import AuthenticationError


def require_workforce_user_id(request: Request) -> UUID:
    """Read only the trusted internal workforce user written to request state."""

    value = getattr(request.state, "serviq_user_id", None)
    if not isinstance(value, UUID):
        raise AuthenticationError
    return value


def require_verified_workforce_identity(request: Request) -> VerifiedWorkforceIdentity:
    """Read only the cryptographically verified workforce identity from request state."""

    value = getattr(request.state, "serviq_workforce_identity", None)
    if not isinstance(value, VerifiedWorkforceIdentity):
        raise AuthenticationError
    return value
