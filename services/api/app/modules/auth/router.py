"""Authentication routes for workforce OIDC integration."""

from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Annotated, Any
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api import SuccessEnvelope
from app.core.auth import WorkforceOidcValidator
from app.core.config import PlatformSettings, load_settings
from app.core.database import get_database_session
from app.core.errors import AuthenticationError
from app.core.session import (
    AUTH_STATE_TTL_SECONDS,
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    STATE_COOKIE_NAME,
    AuthStateData,
    ValkeySessionStore,
    WorkforceSessionData,
    generate_csrf_token,
    get_session_store,
)
from app.modules.auth.dependencies import (
    require_csrf_token,
    require_session_id,
    require_workforce_session,
    validate_csrf_token,
)
from app.modules.auth.schemas import TenantSwitchRequest, WorkforceSessionView
from app.modules.tenancy.errors import TenantMembershipAccessError
from app.modules.tenancy.service import (
    resolve_default_active_tenant_id,
    resolve_tenant_membership,
)
from app.modules.workforce.service import upsert_verified_workforce_user

router = APIRouter(prefix="/auth", tags=["auth"])


def _generate_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code verifier and S256 challenge."""

    code_verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return code_verifier, code_challenge


def _get_cookie_settings(settings: PlatformSettings) -> dict[str, Any]:
    secure = settings.serviq_env in {"staging", "production"}
    return {
        "httponly": True,
        "secure": secure,
        "samesite": "lax",
    }


def _origin(raw_url: str) -> tuple[str, str, int]:
    """Return a normalized HTTP(S) origin or fail closed for unsafe URL forms."""

    try:
        parsed = urlsplit(raw_url)
        port = parsed.port
    except ValueError:
        raise AuthenticationError from None

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise AuthenticationError

    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    return parsed.scheme, parsed.hostname.casefold(), port


def _validate_frontend_redirect_uri(
    redirect_uri: str,
    settings: PlatformSettings,
) -> str:
    """Allow post-login redirects only to the configured public application origin."""

    if _origin(redirect_uri) != _origin(str(settings.serviq_public_base_url)):
        raise AuthenticationError
    return redirect_uri


def _session_view(session_data: WorkforceSessionData) -> WorkforceSessionView:
    return WorkforceSessionView(
        userId=session_data.user_id,
        email=session_data.email,
        displayName=session_data.display_name,
        activeTenantId=session_data.active_tenant_id,
        csrfToken=session_data.csrf_token,
    )


@router.get("/login")
async def login(
    redirect_uri: str = Query(..., description="Post-login frontend destination"),
    settings: PlatformSettings = Depends(load_settings),  # noqa: B008
    session_store: ValkeySessionStore = Depends(get_session_store),  # noqa: B008
) -> RedirectResponse:
    """Start the OIDC Authorization Code flow with PKCE."""

    safe_redirect_uri = _validate_frontend_redirect_uri(redirect_uri, settings)
    state_id = secrets.token_urlsafe(16)
    code_verifier, code_challenge = _generate_pkce_pair()

    await session_store.save_auth_state(
        state_id,
        AuthStateData(code_verifier=code_verifier, redirect_uri=safe_redirect_uri),
    )

    auth_url = str(settings.oidc_issuer_url).rstrip("/") + "/protocol/openid-connect/auth"
    query = httpx.QueryParams(
        {
            "client_id": settings.oidc_client_id,
            "response_type": "code",
            "redirect_uri": str(settings.oidc_redirect_uri),
            "state": state_id,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "scope": "openid email profile",
        }
    )
    redirect = RedirectResponse(f"{auth_url}?{query}")

    redirect.set_cookie(
        STATE_COOKIE_NAME,
        state_id,
        max_age=AUTH_STATE_TTL_SECONDS,
        **_get_cookie_settings(settings),
    )
    return redirect


@router.get("/callback")
async def callback(
    code: str = Query(...),
    state: str = Query(...),
    serviq_auth_state: Annotated[str | None, Cookie()] = None,
    settings: PlatformSettings = Depends(load_settings),  # noqa: B008
    session_store: ValkeySessionStore = Depends(get_session_store),  # noqa: B008
    db: AsyncSession = Depends(get_database_session),  # noqa: B008
) -> RedirectResponse:
    """Complete OIDC, resolve the workforce user, and establish an opaque session."""

    if serviq_auth_state is None or not secrets.compare_digest(state, serviq_auth_state):
        raise AuthenticationError

    auth_state = await session_store.consume_auth_state(state)
    token_url = str(settings.oidc_issuer_url).rstrip("/") + "/protocol/openid-connect/token"

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            token_response = await client.post(
                token_url,
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.oidc_client_id,
                    "client_secret": settings.oidc_client_secret.get_secret_value(),
                    "code": code,
                    "redirect_uri": str(settings.oidc_redirect_uri),
                    "code_verifier": auth_state.code_verifier,
                },
            )
            token_response.raise_for_status()
            payload = token_response.json()
        except httpx.HTTPError, ValueError:
            raise AuthenticationError from None

    if not isinstance(payload, dict):
        raise AuthenticationError
    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise AuthenticationError

    verified_identity = await WorkforceOidcValidator(settings).validate(access_token)
    internal_user = await upsert_verified_workforce_user(db, verified_identity)
    if internal_user.status != "active":
        raise AuthenticationError

    active_tenant_id = await resolve_default_active_tenant_id(
        db,
        user_id=internal_user.id,
    )
    session_data = WorkforceSessionData(
        user_id=internal_user.id,
        oidc_subject=verified_identity.subject,
        oidc_issuer=verified_identity.issuer,
        email=verified_identity.email,
        email_verified=verified_identity.email_verified,
        display_name=verified_identity.display_name,
        active_tenant_id=active_tenant_id,
        csrf_token=generate_csrf_token(),
    )
    session_id = await session_store.create_session(session_data)

    redirect = RedirectResponse(auth_state.redirect_uri)
    cookie_settings = _get_cookie_settings(settings)
    redirect.set_cookie(
        SESSION_COOKIE_NAME,
        session_id,
        max_age=SESSION_TTL_SECONDS,
        **cookie_settings,
    )
    redirect.delete_cookie(STATE_COOKIE_NAME, **cookie_settings)
    return redirect


@router.get("/session", response_model=SuccessEnvelope[WorkforceSessionView])
async def get_current_session(
    session_data: Annotated[WorkforceSessionData, Depends(require_workforce_session)],
) -> SuccessEnvelope[WorkforceSessionView]:
    """Return browser-safe session state for the authenticated client console."""

    return SuccessEnvelope(data=_session_view(session_data))


@router.post("/tenant", response_model=SuccessEnvelope[WorkforceSessionView])
async def switch_active_tenant(
    body: TenantSwitchRequest,
    request: Request,
    session_data: Annotated[WorkforceSessionData, Depends(require_csrf_token)],
    session_id: Annotated[str, Depends(require_session_id)],
    session_store: ValkeySessionStore = Depends(get_session_store),  # noqa: B008
    db: AsyncSession = Depends(get_database_session),  # noqa: B008
) -> SuccessEnvelope[WorkforceSessionView] | JSONResponse:
    """Select an active tenant only after authoritative membership validation."""

    try:
        await resolve_tenant_membership(
            db,
            user_id=session_data.user_id,
            tenant_id=body.tenant_id,
        )
    except TenantMembershipAccessError:
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "code": "TENANT_MEMBERSHIP_REQUIRED",
                    "message": "Active tenant membership is required.",
                }
            },
        )

    updated_session = session_data.model_copy(update={"active_tenant_id": body.tenant_id})
    await session_store.replace_session(session_id, updated_session)
    request.state.serviq_session = updated_session
    request.state.serviq_tenant_id = body.tenant_id
    return SuccessEnvelope(data=_session_view(updated_session))


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    x_serviq_csrf_token: Annotated[str | None, Header(alias=CSRF_HEADER_NAME)] = None,
    session_store: ValkeySessionStore = Depends(get_session_store),  # noqa: B008
    settings: PlatformSettings = Depends(load_settings),  # noqa: B008
) -> Response:
    """Destroy a valid session with CSRF proof; stale cookies clear idempotently."""

    session_data = getattr(request.state, "serviq_session", None)
    session_id = getattr(request.state, "serviq_session_id", None)
    if isinstance(session_data, WorkforceSessionData) and isinstance(session_id, str):
        validate_csrf_token(session_data, x_serviq_csrf_token)
        await session_store.destroy_session(session_id)

    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE_NAME, **_get_cookie_settings(settings))
    return response
