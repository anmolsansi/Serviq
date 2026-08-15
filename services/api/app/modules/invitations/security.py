"""Invitation secret and identity-normalization helpers frozen by ADR-006."""

import hashlib
import secrets
from urllib.parse import urlencode


class InvitationEmailError(ValueError):
    """The invitee email cannot be normalized under the V1 contract."""


def normalize_invitation_email(value: str) -> str:
    normalized = value.strip().casefold()
    if not 3 <= len(normalized) <= 320:
        raise InvitationEmailError("email must be 3-320 characters after normalization")
    if any(character.isspace() for character in normalized):
        raise InvitationEmailError("email cannot contain whitespace")
    if normalized.count("@") != 1:
        raise InvitationEmailError("email must contain exactly one @")
    local, domain = normalized.split("@", 1)
    if not local or not domain:
        raise InvitationEmailError("email local and domain parts are required")
    if domain.startswith(".") or domain.endswith(".") or ".." in domain:
        raise InvitationEmailError("email domain is invalid")
    return normalized


def generate_invitation_token() -> str:
    """Generate 256 bits of cryptographically secure random bearer material."""

    return secrets.token_urlsafe(32)


def hash_invitation_token(token: str) -> str:
    """Return the persisted one-way digest; never log token or digest."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def build_invitation_url(public_base_url: str, token: str) -> str:
    base = public_base_url.rstrip("/")
    return f"{base}/invite?{urlencode({'token': token})}"
