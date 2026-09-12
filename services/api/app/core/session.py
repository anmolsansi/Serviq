"""Valkey-backed stateful session storage for workforce authentication."""

import json
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

import valkey.asyncio as valkey
from fastapi import Request
from pydantic import BaseModel, ConfigDict
from valkey.exceptions import ValkeyError

from app.core.config import load_settings
from app.core.errors import AuthenticationError
from app.core.rate_limits import _normalize_valkey_url

SESSION_COOKIE_NAME = "serviq_session"
STATE_COOKIE_NAME = "serviq_auth_state"
SESSION_TTL_SECONDS = 86400  # 24 hours
AUTH_STATE_TTL_SECONDS = 600  # 10 minutes


class SessionUnavailableError(RuntimeError):
    """Raised when Valkey is unavailable for session storage."""

    error_code = "SESSION_STORE_UNAVAILABLE"

    def __init__(self) -> None:
        super().__init__("Session storage is temporarily unavailable.")


class WorkforceSessionData(BaseModel):
    """Trusted session data stored in Valkey."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    user_id: UUID
    oidc_subject: str
    oidc_issuer: str
    email: str | None = None
    email_verified: bool = False


class AuthStateData(BaseModel):
    """Short-lived PKCE state stored in Valkey during login flow."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code_verifier: str
    redirect_uri: str


class ValkeySessionStore:
    """Manages PKCE state and workforce sessions in Valkey."""

    def __init__(self, client: valkey.Valkey) -> None:
        self._client = client

    async def save_auth_state(self, state_id: str, data: AuthStateData) -> None:
        """Store PKCE auth state temporarily."""
        key = f"serviq:auth:state:{state_id}"
        try:
            await self._client.setex(key, AUTH_STATE_TTL_SECONDS, data.model_dump_json())
        except ValkeyError:
            raise SessionUnavailableError from None

    async def consume_auth_state(self, state_id: str) -> AuthStateData:
        """Retrieve and immediately delete PKCE auth state."""
        key = f"serviq:auth:state:{state_id}"
        try:
            raw = await self._client.getdel(key)
        except ValkeyError:
            raise SessionUnavailableError from None

        if not raw:
            raise AuthenticationError

        try:
            payload = json.loads(raw)
            return AuthStateData.model_validate(payload)
        except ValueError, TypeError:
            raise AuthenticationError from None

    async def create_session(self, data: WorkforceSessionData) -> str:
        """Create a new session and return the secure session ID."""
        session_id = secrets.token_urlsafe(32)
        key = f"serviq:session:{session_id}"
        try:
            await self._client.setex(key, SESSION_TTL_SECONDS, data.model_dump_json())
        except ValkeyError:
            raise SessionUnavailableError from None
        return session_id

    async def get_session(self, session_id: str) -> WorkforceSessionData | None:
        """Retrieve session data by session ID."""
        key = f"serviq:session:{session_id}"
        try:
            raw = await self._client.get(key)
        except ValkeyError:
            raise SessionUnavailableError from None

        if not raw:
            return None

        try:
            payload = json.loads(raw)
            return WorkforceSessionData.model_validate(payload)
        except ValueError, TypeError:
            return None

    async def destroy_session(self, session_id: str) -> None:
        """Delete a session."""
        import contextlib

        key = f"serviq:session:{session_id}"
        with contextlib.suppress(ValkeyError):
            await self._client.delete(key)


_global_valkey_pool: valkey.Valkey | None = None


@asynccontextmanager
async def lifespan_session_store() -> AsyncGenerator[None]:
    """Manage the Valkey connection pool for sessions."""
    global _global_valkey_pool
    settings = load_settings()
    try:
        url = _normalize_valkey_url(settings)
        _global_valkey_pool = valkey.from_url(  # type: ignore[no-untyped-call]
            url,
            decode_responses=True,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
            health_check_interval=30,
        )
        yield
    finally:
        if _global_valkey_pool:
            await _global_valkey_pool.aclose()
            _global_valkey_pool = None


def get_session_store(request: Request) -> ValkeySessionStore:
    """Dependency for injecting the session store."""
    if _global_valkey_pool is None:
        raise SessionUnavailableError
    return ValkeySessionStore(_global_valkey_pool)
