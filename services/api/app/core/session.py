"""Valkey-backed stateful session storage for workforce authentication."""

from __future__ import annotations

import json
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast
from uuid import UUID

import valkey.asyncio as valkey
from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field
from valkey.exceptions import ValkeyError

from app.core.config import load_settings
from app.core.errors import AuthenticationError
from app.core.rate_limits import _normalize_valkey_url

SESSION_COOKIE_NAME = "serviq_session"
STATE_COOKIE_NAME = "serviq_auth_state"
CSRF_HEADER_NAME = "X-Serviq-CSRF-Token"
SESSION_TTL_SECONDS = 86400  # 24 hours
AUTH_STATE_TTL_SECONDS = 600  # 10 minutes


class SessionUnavailableError(RuntimeError):
    """Raised when Valkey is unavailable for session storage."""

    error_code = "SESSION_STORE_UNAVAILABLE"

    def __init__(self) -> None:
        super().__init__("Session storage is temporarily unavailable.")


class WorkforceSessionData(BaseModel):
    """Trusted session data stored only on the server side."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    user_id: UUID
    oidc_subject: str
    oidc_issuer: str
    email: str | None = None
    email_verified: bool = False
    display_name: str | None = None
    active_tenant_id: UUID | None = None
    csrf_token: str = Field(min_length=32)


class AuthStateData(BaseModel):
    """Short-lived PKCE state stored in Valkey during login flow."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code_verifier: str
    redirect_uri: str


def generate_csrf_token() -> str:
    """Create a high-entropy token bound to one server-side workforce session."""

    return secrets.token_urlsafe(32)


class ValkeySessionStore:
    """Manage one-time PKCE state and opaque workforce sessions in Valkey."""

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
        """Retrieve and immediately delete one PKCE auth-state record."""

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
        """Create a new opaque session and return its browser cookie value."""

        session_id = secrets.token_urlsafe(32)
        key = f"serviq:session:{session_id}"
        try:
            await self._client.setex(key, SESSION_TTL_SECONDS, data.model_dump_json())
        except ValkeyError:
            raise SessionUnavailableError from None
        return session_id

    async def get_session(self, session_id: str) -> WorkforceSessionData | None:
        """Retrieve one session. Missing, expired, or malformed records are invalid."""

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

    async def replace_session(self, session_id: str, data: WorkforceSessionData) -> None:
        """Replace an existing session atomically while preserving its remaining TTL."""

        key = f"serviq:session:{session_id}"
        try:
            updated = await self._client.set(
                key,
                data.model_dump_json(),
                xx=True,
                keepttl=True,
            )
        except ValkeyError:
            raise SessionUnavailableError from None
        if not updated:
            raise AuthenticationError

    async def destroy_session(self, session_id: str) -> None:
        """Delete a session, failing closed when the session store is unavailable."""

        key = f"serviq:session:{session_id}"
        try:
            await self._client.delete(key)
        except ValkeyError:
            raise SessionUnavailableError from None


@asynccontextmanager
async def lifespan_session_store() -> AsyncGenerator[ValkeySessionStore]:
    """Create and close the process-shared Valkey client used for sessions."""

    settings = load_settings()
    client = valkey.from_url(  # type: ignore[no-untyped-call]
        _normalize_valkey_url(settings),
        decode_responses=True,
        socket_connect_timeout=2.0,
        socket_timeout=2.0,
        health_check_interval=30,
    )
    try:
        yield ValkeySessionStore(client)
    finally:
        await client.aclose()


def get_session_store(request: Request) -> ValkeySessionStore:
    """Return the app-owned session store or fail safely outside application lifespan."""

    store = getattr(request.app.state, "session_store", None)
    if store is None:
        raise SessionUnavailableError
    return cast(ValkeySessionStore, store)
