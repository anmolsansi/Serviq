"""Shared Valkey-backed rate-limit boundary for bounded provider connectivity tests."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol, cast
from uuid import UUID

import valkey.asyncio as valkey
from valkey.exceptions import ValkeyError

from app.core.config import PlatformSettings, load_settings

_PROVIDER_TEST_USER_LIMIT = 10
_PROVIDER_TEST_USER_WINDOW_SECONDS = 60
_PROVIDER_TEST_CONNECTION_LIMIT = 30
_PROVIDER_TEST_CONNECTION_WINDOW_SECONDS = 3_600

# Check and consume both frozen limits atomically so concurrent workers cannot race
# between separate GET/INCR operations.
_PROVIDER_TEST_SCRIPT = """
local user_count = tonumber(redis.call('GET', KEYS[1]) or '0')
local connection_count = tonumber(redis.call('GET', KEYS[2]) or '0')
local user_limit = tonumber(ARGV[1])
local connection_limit = tonumber(ARGV[2])
local user_window = tonumber(ARGV[3])
local connection_window = tonumber(ARGV[4])

if user_count >= user_limit or connection_count >= connection_limit then
  local user_ttl = redis.call('TTL', KEYS[1])
  local connection_ttl = redis.call('TTL', KEYS[2])
  if user_ttl < 1 then user_ttl = 1 end
  if connection_ttl < 1 then connection_ttl = 1 end
  local retry_after = user_ttl
  if connection_ttl > retry_after then retry_after = connection_ttl end
  return {0, retry_after}
end

local new_user_count = redis.call('INCR', KEYS[1])
if new_user_count == 1 then redis.call('EXPIRE', KEYS[1], user_window) end
local new_connection_count = redis.call('INCR', KEYS[2])
if new_connection_count == 1 then redis.call('EXPIRE', KEYS[2], connection_window) end
return {1, 0}
"""


class RateLimitUnavailableError(RuntimeError):
    """Safe failure raised when shared abuse-control state cannot be enforced."""

    error_code = "PROVIDER_TEST_UNAVAILABLE"

    def __init__(self) -> None:
        super().__init__("Provider connectivity testing is temporarily unavailable.")


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int | None = None


class ProviderTestRateLimiter(Protocol):
    async def check_and_consume(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        provider_connection_id: UUID,
    ) -> RateLimitDecision: ...


class _AsyncValkeyEvalClient(Protocol):
    async def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: object,
    ) -> object: ...


class ValkeyProviderTestRateLimiter:
    """Enforce the two frozen provider-test limits using process-shared Valkey state."""

    def __init__(self, client: _AsyncValkeyEvalClient) -> None:
        self._client = client

    async def check_and_consume(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        provider_connection_id: UUID,
    ) -> RateLimitDecision:
        user_key = f"serviq:rate:provider-test:user:{tenant_id}:{user_id}"
        connection_key = (
            f"serviq:rate:provider-test:connection:{tenant_id}:{provider_connection_id}"
        )
        try:
            raw_result = await self._client.eval(
                _PROVIDER_TEST_SCRIPT,
                2,
                user_key,
                connection_key,
                _PROVIDER_TEST_USER_LIMIT,
                _PROVIDER_TEST_CONNECTION_LIMIT,
                _PROVIDER_TEST_USER_WINDOW_SECONDS,
                _PROVIDER_TEST_CONNECTION_WINDOW_SECONDS,
            )
        except ValkeyError:
            raise RateLimitUnavailableError from None

        result = cast(list[object], raw_result)
        if len(result) != 2:
            raise RateLimitUnavailableError
        try:
            allowed = int(cast(int | bytes | str, result[0])) == 1
            retry_after = int(cast(int | bytes | str, result[1]))
        except (TypeError, ValueError):
            raise RateLimitUnavailableError from None

        return RateLimitDecision(
            allowed=allowed,
            retry_after_seconds=None if allowed else max(retry_after, 1),
        )


def _normalize_valkey_url(settings: PlatformSettings) -> str:
    raw = str(settings.valkey_url)
    if raw.startswith("valkey://"):
        return raw.replace("valkey://", "redis://", 1)
    if raw.startswith(("redis://", "rediss://")):
        return raw
    raise RateLimitUnavailableError


def build_provider_test_rate_limiter(settings: PlatformSettings) -> ValkeyProviderTestRateLimiter:
    """Build the process-shared async client from the frozen platform VALKEY_URL."""

    # valkey-py 6.1.1's public from_url() factory has no return annotation.
    # Keep that third-party typing gap confined to this single adapter boundary.
    client = cast(
        _AsyncValkeyEvalClient,
        valkey.from_url(  # type: ignore[no-untyped-call]
            _normalize_valkey_url(settings),
            decode_responses=False,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
            health_check_interval=30,
        ),
    )
    return ValkeyProviderTestRateLimiter(client)


@lru_cache(maxsize=1)
def get_provider_test_rate_limiter() -> ValkeyProviderTestRateLimiter:
    """Return one pooled Valkey client per API process."""

    return build_provider_test_rate_limiter(load_settings())
