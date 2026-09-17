"""Trusted workforce authentication and request-context primitives.

This module owns Architecture Contract C-1 plus the OPE-280 workforce OIDC token
validation boundary. It never accepts tenant IDs or permissions from token claims.
Browser PKCE/session behavior and membership resolution remain separate concerns.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Annotated, Any, cast
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet, KeySetSerialization
from joserfc.jwt import JWTClaimsRegistry
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import PlatformSettings, ServiqEnvironment
from app.core.errors import AuthenticationError, MissingTenantContextError

NonEmptyString = Annotated[str, Field(min_length=1)]
JsonFetcher = Callable[[str, str], Awaitable[dict[str, Any]]]
Clock = Callable[[], float]

OIDC_METADATA_CACHE_TTL_SECONDS = 300.0
OIDC_HTTP_TIMEOUT_SECONDS = 5.0
OIDC_MAX_METADATA_BYTES = 1_000_000
OIDC_DISCOVERY_RELATIVE_PATH = ".well-known/openid-configuration"
OIDC_JWKS_RELATIVE_PATH = "protocol/openid-connect/certs"
OIDC_TOKEN_RELATIVE_PATH = "protocol/openid-connect/token"
OIDC_AUTH_RELATIVE_PATH = "protocol/openid-connect/auth"
WORKFORCE_JWT_ALGORITHMS: tuple[str, ...] = ("RS256",)
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class ActorType(StrEnum):
    """Strict actor categories allowed by Architecture Contract C-1."""

    TENANT_USER = "tenant_user"
    CUSTOMER = "customer"
    SERVICE = "service"
    PLATFORM_OPERATOR = "platform_operator"


class AssuranceLevel(StrEnum):
    """Strict identity-assurance levels allowed by Architecture Contract C-1."""

    ANONYMOUS = "anonymous"
    VERIFIED = "verified"
    WORKFORCE = "workforce"
    PLATFORM = "platform"


class RequestActor(BaseModel):
    """Trusted actor identity nested inside a request context."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    type: ActorType
    id: NonEmptyString


class RequestContext(BaseModel):
    """Immutable trusted request context matching Architecture Contract C-1."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    request_id: NonEmptyString = Field(alias="requestId")
    tenant_id: UUID = Field(alias="tenantId")
    actor: RequestActor
    user_id: UUID | None = Field(default=None, alias="userId")
    customer_id: UUID | None = Field(default=None, alias="customerId")
    permissions: tuple[str, ...] = ()
    assurance_level: AssuranceLevel = Field(alias="assuranceLevel")

    def has_permission(self, permission: str) -> bool:
        """Return whether the trusted capability set contains ``permission``."""

        return permission in self.permissions


class VerifiedWorkforceIdentity(BaseModel):
    """Small trusted identity DTO returned only after OIDC verification succeeds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    issuer: NonEmptyString
    subject: NonEmptyString
    email: str | None = None
    email_verified: bool = False
    display_name: str | None = None


def validated_oidc_issuer_base(
    issuer: str,
    environment: ServiqEnvironment,
) -> str:
    """Validate and normalize the configured OIDC issuer before any outbound request.

    Production-like environments require HTTPS. Local and test environments may
    use HTTP only for an explicit loopback issuer. Userinfo, query strings, and
    fragments are never accepted at this trust boundary.
    """

    try:
        parsed = urlsplit(issuer)
        port = parsed.port
    except ValueError:
        raise AuthenticationError from None

    if (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise AuthenticationError

    if parsed.scheme == "https":
        if port not in (None, 443):
            raise AuthenticationError
    elif (
        environment in {"local", "test"}
        and parsed.scheme == "http"
        and parsed.hostname in _LOOPBACK_HOSTS
        and port in (None, 80, 8080)
    ):
        pass
    else:
        raise AuthenticationError

    normalized_path = parsed.path.rstrip("/")
    authority = parsed.hostname.casefold()
    if ":" in authority and not authority.startswith("["):
        authority = f"[{authority}]"
    if port is not None and not (
        parsed.scheme == "https" and port == 443 or parsed.scheme == "http" and port == 80
    ):
        authority = f"{authority}:{port}"
    return f"{parsed.scheme}://{authority}{normalized_path}"


async def _fetch_oidc_json(issuer_base: str, relative_path: str) -> dict[str, Any]:
    """Fetch bounded OIDC JSON from one validated issuer using a relative endpoint."""

    if relative_path not in {OIDC_DISCOVERY_RELATIVE_PATH, OIDC_JWKS_RELATIVE_PATH}:
        raise AuthenticationError

    try:
        timeout = httpx.Timeout(OIDC_HTTP_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(
            base_url=f"{issuer_base}/",
            timeout=timeout,
            follow_redirects=False,
        ) as client:
            response = await client.get(relative_path, headers={"Accept": "application/json"})
            response.raise_for_status()
            if len(response.content) > OIDC_MAX_METADATA_BYTES:
                raise AuthenticationError
            payload = response.json()
    except AuthenticationError:
        raise
    except httpx.HTTPError, ValueError:
        raise AuthenticationError from None

    if not isinstance(payload, dict):
        raise AuthenticationError
    return cast(dict[str, Any], payload)


def _as_key_set_serialization(payload: dict[str, Any]) -> KeySetSerialization:
    keys = payload.get("keys")
    if not isinstance(keys, list) or not keys:
        raise AuthenticationError
    if not all(isinstance(key, dict) for key in keys):
        raise AuthenticationError
    return cast(KeySetSerialization, payload)


class OidcMetadataCache:
    """Small process-local, single-flight cache for trusted issuer discovery/JWKS."""

    def __init__(
        self,
        *,
        issuer: str,
        environment: ServiqEnvironment,
        fetcher: JsonFetcher = _fetch_oidc_json,
        ttl_seconds: float = OIDC_METADATA_CACHE_TTL_SECONDS,
        clock: Clock = time.monotonic,
    ) -> None:
        self._issuer = validated_oidc_issuer_base(issuer, environment)
        self._fetcher = fetcher
        self._ttl_seconds = min(max(ttl_seconds, 1.0), OIDC_METADATA_CACHE_TTL_SECONDS)
        self._clock = clock
        self._key_set: KeySet | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def get_key_set(self) -> KeySet:
        """Return cached issuer keys, fetching discovery and JWKS only when needed."""

        now = self._clock()
        if self._key_set is not None and now < self._expires_at:
            return self._key_set

        async with self._lock:
            now = self._clock()
            if self._key_set is not None and now < self._expires_at:
                return self._key_set

            try:
                discovery = await self._fetcher(self._issuer, OIDC_DISCOVERY_RELATIVE_PATH)
                if discovery.get("issuer") != self._issuer:
                    raise AuthenticationError

                expected_jwks_uri = f"{self._issuer}/{OIDC_JWKS_RELATIVE_PATH}"
                if discovery.get("jwks_uri") != expected_jwks_uri:
                    raise AuthenticationError

                jwks = await self._fetcher(self._issuer, OIDC_JWKS_RELATIVE_PATH)
                key_set = KeySet.import_key_set(_as_key_set_serialization(jwks))
            except AuthenticationError:
                raise
            except Exception:
                raise AuthenticationError from None

            self._key_set = key_set
            self._expires_at = self._clock() + self._ttl_seconds
            return key_set


class WorkforceOidcValidator:
    """Validate configured workforce OIDC JWTs and expose only trusted identity data."""

    def __init__(
        self,
        settings: PlatformSettings,
        *,
        metadata_cache: OidcMetadataCache | None = None,
    ) -> None:
        self._issuer = validated_oidc_issuer_base(str(settings.oidc_issuer_url), settings.serviq_env)
        self._audience = settings.oidc_client_id
        self._metadata_cache = metadata_cache or OidcMetadataCache(
            issuer=self._issuer,
            environment=settings.serviq_env,
        )

    async def validate(self, raw_token: str) -> VerifiedWorkforceIdentity:
        """Return verified workforce identity or one safe fail-closed error."""

        if not raw_token or not raw_token.strip():
            raise AuthenticationError

        try:
            key_set = await self._metadata_cache.get_key_set()
            decoded = jwt.decode(
                raw_token,
                key_set,
                algorithms=WORKFORCE_JWT_ALGORITHMS,
            )
            claims = decoded.claims
            registry = JWTClaimsRegistry(
                iss={"essential": True, "value": self._issuer},
                aud={"essential": True, "value": self._audience},
                exp={"essential": True},
                sub={"essential": True},
            )
            registry.validate(claims)
        except AuthenticationError:
            raise
        except JoseError, KeyError, TypeError, ValueError:
            raise AuthenticationError from None

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise AuthenticationError

        email = _optional_string(claims.get("email"), lower=True)
        email_verified = claims.get("email_verified") is True
        display_name = _optional_string(claims.get("name")) or _optional_string(
            claims.get("preferred_username")
        )

        return VerifiedWorkforceIdentity(
            issuer=self._issuer,
            subject=subject.strip(),
            email=email,
            email_verified=email_verified,
            display_name=display_name,
        )


def _optional_string(value: object, *, lower: bool = False) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized.casefold() if lower else normalized


def require_tenant_id(context: RequestContext | None) -> UUID:
    """Return trusted tenant ID or fail closed when no trusted context exists."""

    if context is None:
        raise MissingTenantContextError
    return context.tenant_id
