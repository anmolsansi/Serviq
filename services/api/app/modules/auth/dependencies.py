"""Trusted workforce-session request composition and CSRF dependencies."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Header, Request

from app.core.auth import VerifiedWorkforceIdentity
from app.core.errors import AuthenticationError, CsrfValidationError
from app.core.session import (
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    ValkeySessionStore,
    WorkforceSessionData,
)


async def restore_request_session_context(
    request: Request,
    session_store: ValkeySessionStore,
) -> WorkforceSessionData | None:
    """Restore server-owned workforce and tenant state from an opaque session cookie."""

    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        return None

    session_data = await session_store.get_session(session_id)
    if session_data is None:
        return None

    request.state.serviq_session_id = session_id
    request.state.serviq_session = session_data
    request.state.serviq_user_id = session_data.user_id
    request.state.serviq_workforce_identity = VerifiedWorkforceIdentity(
        subject=session_data.oidc_subject,
        issuer=session_data.oidc_issuer,
        email=session_data.email,
        email_verified=session_data.email_verified,
        display_name=session_data.display_name,
    )
    if session_data.active_tenant_id is not None:
        request.state.serviq_tenant_id = session_data.active_tenant_id

    return session_data


def require_workforce_session(request: Request) -> WorkforceSessionData:
    """Require session data that was restored from the server-side session store."""

    value = getattr(request.state, "serviq_session", None)
    if not isinstance(value, WorkforceSessionData):
        raise AuthenticationError
    return value


def require_session_id(request: Request) -> str:
    """Return the opaque session identifier only after middleware restored it."""

    value = getattr(request.state, "serviq_session_id", None)
    if not isinstance(value, str) or not value:
        raise AuthenticationError
    return value


def validate_csrf_token(
    session_data: WorkforceSessionData,
    supplied_token: str | None,
) -> None:
    """Validate state-changing browser requests against the session-bound CSRF token."""

    if supplied_token is None or not secrets.compare_digest(
        supplied_token,
        session_data.csrf_token,
    ):
        raise CsrfValidationError


def require_csrf_token(
    session_data: Annotated[WorkforceSessionData, Depends(require_workforce_session)],
    x_serviq_csrf_token: Annotated[str | None, Header(alias=CSRF_HEADER_NAME)] = None,
) -> WorkforceSessionData:
    """Require an authenticated session and matching CSRF proof."""

    validate_csrf_token(session_data, x_serviq_csrf_token)
    return session_data
