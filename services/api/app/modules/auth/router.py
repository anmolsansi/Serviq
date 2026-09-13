"""Authentication routes for workforce OIDC integration."""

import base64
import hashlib
import secrets
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Cookie, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api import SuccessEnvelope
from app.core.auth import WorkforceOidcValidator
from app.core.config import PlatformSettings, load_settings
from app.core.database import get_database_session
from app.core.errors import AuthenticationError
from app.core.session import (
    SESSION_COOKIE_NAME,
    STATE_COOKIE_NAME,
    AuthStateData,
    ValkeySessionStore,
    WorkforceSessionData,
    get_session_store,
)
from app.modules.workforce.service import upsert_verified_workforce_user

router = APIRouter(prefix="/auth", tags=["auth"])


def _generate_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier and code_challenge."""
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


@router.get("/login")
async def login(
    request: Request,
    response: Response,
    redirect_uri: str = Query(..., description="Frontend callback URI"),
    settings: PlatformSettings = Depends(load_settings),  # noqa: B008
    session_store: ValkeySessionStore = Depends(get_session_store),  # noqa: B008
) -> RedirectResponse:
    """Start the OIDC Authorization Code flow with PKCE."""
    # Ensure redirect_uri is allowed (e.g. starts with public base URL)
    public_base = str(settings.serviq_public_base_url).rstrip("/")
    if (
        not redirect_uri.startswith(public_base)
        and settings.serviq_env != "local"
        and settings.serviq_env in {"production", "staging"}
    ):
        raise AuthenticationError

    state_id = secrets.token_urlsafe(16)
    code_verifier, code_challenge = _generate_pkce_pair()

    await session_store.save_auth_state(
        state_id,
        AuthStateData(code_verifier=code_verifier, redirect_uri=redirect_uri),
    )

    auth_url = str(settings.oidc_issuer_url).rstrip("/") + "/protocol/openid-connect/auth"
    params = {
        "client_id": settings.oidc_client_id,
        "response_type": "code",
        "redirect_uri": str(settings.oidc_redirect_uri),
        "state": state_id,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "scope": "openid email profile",
    }

    query = "&".join(
        f"{k}={httpx.QueryParams({k: v}).__str__().split('=')[1]}" for k, v in params.items()
    )
    redirect = RedirectResponse(f"{auth_url}?{query}")

    cookie_settings = _get_cookie_settings(settings)
    redirect.set_cookie(STATE_COOKIE_NAME, state_id, max_age=600, **cookie_settings)
    return redirect


@router.get("/callback")
async def callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    serviq_auth_state: Annotated[str | None, Cookie()] = None,
    settings: PlatformSettings = Depends(load_settings),  # noqa: B008
    session_store: ValkeySessionStore = Depends(get_session_store),  # noqa: B008
    db: AsyncSession = Depends(get_database_session),  # noqa: B008
) -> RedirectResponse:
    """Complete the OIDC flow, exchange code, validate, and establish a session."""
    if serviq_auth_state is None or state != serviq_auth_state:
        raise AuthenticationError

    # Consume state (throws AuthenticationError if invalid or expired)
    auth_state = await session_store.consume_auth_state(state)

    token_url = str(settings.oidc_issuer_url).rstrip("/") + "/protocol/openid-connect/token"

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            token_res = await client.post(
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
            token_res.raise_for_status()
            payload = token_res.json()
        except httpx.HTTPError, ValueError:
            raise AuthenticationError from None

    access_token = payload.get("access_token")
    if not access_token:
        raise AuthenticationError

    # Validate the JWT using the existing workforce validator
    validator = WorkforceOidcValidator(settings)
    verified_identity = await validator.validate(access_token)

    # Resolve to an internal user
    internal_user = await upsert_verified_workforce_user(db, verified_identity)
    if internal_user.status != "active":
        raise AuthenticationError

    # Create session
    session_id = await session_store.create_session(
        WorkforceSessionData(
            user_id=internal_user.id,
            oidc_subject=verified_identity.subject,
            oidc_issuer=verified_identity.issuer,
            email=verified_identity.email,
            email_verified=verified_identity.email_verified,
        )
    )

    redirect = RedirectResponse(auth_state.redirect_uri)
    cookie_settings = _get_cookie_settings(settings)
    redirect.set_cookie(SESSION_COOKIE_NAME, session_id, max_age=86400, **cookie_settings)
    redirect.delete_cookie(STATE_COOKIE_NAME, **cookie_settings)
    return redirect


@router.post("/logout")
async def logout(
    request: Request,
    serviq_session: Annotated[str | None, Cookie()] = None,
    session_store: ValkeySessionStore = Depends(get_session_store),  # noqa: B008
    settings: PlatformSettings = Depends(load_settings),  # noqa: B008
) -> SuccessEnvelope[dict[str, str]]:
    """Destroy the current session."""
    if serviq_session:
        await session_store.destroy_session(serviq_session)

    response = Response(status_code=204)
    cookie_settings = _get_cookie_settings(settings)
    response.delete_cookie(SESSION_COOKIE_NAME, **cookie_settings)
    return response  # type: ignore
