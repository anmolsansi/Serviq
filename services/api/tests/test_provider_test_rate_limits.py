from __future__ import annotations

import asyncio
from uuid import UUID

import pytest
from valkey.exceptions import ConnectionError as ValkeyConnectionError

from app.core.rate_limits import (
    RateLimitUnavailableError,
    ValkeyProviderTestRateLimiter,
)

TENANT_ID = UUID("00000000-0000-0000-0000-000000000101")
USER_ID = UUID("00000000-0000-0000-0000-000000000102")
CONNECTION_ID = UUID("00000000-0000-0000-0000-000000000103")


class FakeEvalClient:
    def __init__(self, result: object = (1, 0), *, fail: bool = False) -> None:
        self.result = result
        self.fail = fail
        self.calls: list[tuple[str, int, tuple[object, ...]]] = []

    async def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: object,
    ) -> object:
        self.calls.append((script, numkeys, keys_and_args))
        if self.fail:
            raise ValkeyConnectionError("unsafe valkey transport detail")
        return self.result


def test_provider_test_limits_are_checked_and_consumed_as_one_atomic_decision() -> None:
    async def scenario() -> None:
        client = FakeEvalClient([1, 0])
        limiter = ValkeyProviderTestRateLimiter(client)
        decision = await limiter.check_and_consume(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            provider_connection_id=CONNECTION_ID,
        )

        assert decision.allowed is True
        assert decision.retry_after_seconds is None
        assert len(client.calls) == 1
        script, numkeys, args = client.calls[0]
        assert "GET" in script
        assert "INCR" in script
        assert "EXPIRE" in script
        assert numkeys == 2
        assert args == (
            f"serviq:rate:provider-test:user:{TENANT_ID}:{USER_ID}",
            f"serviq:rate:provider-test:connection:{TENANT_ID}:{CONNECTION_ID}",
            10,
            30,
            60,
            3_600,
        )
        assert "sk-" not in repr(args)

    asyncio.run(scenario())


def test_provider_test_limit_rejection_preserves_retry_after() -> None:
    async def scenario() -> None:
        limiter = ValkeyProviderTestRateLimiter(FakeEvalClient([0, 47]))
        decision = await limiter.check_and_consume(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            provider_connection_id=CONNECTION_ID,
        )
        assert decision.allowed is False
        assert decision.retry_after_seconds == 47

    asyncio.run(scenario())


def test_provider_test_limit_store_failure_fails_closed_without_raw_detail() -> None:
    async def scenario() -> None:
        limiter = ValkeyProviderTestRateLimiter(FakeEvalClient(fail=True))
        with pytest.raises(RateLimitUnavailableError) as captured:
            await limiter.check_and_consume(
                tenant_id=TENANT_ID,
                user_id=USER_ID,
                provider_connection_id=CONNECTION_ID,
            )
        assert "unsafe valkey transport detail" not in str(captured.value)

    asyncio.run(scenario())


def test_provider_test_limit_malformed_store_response_fails_closed() -> None:
    async def scenario() -> None:
        for malformed in ([], [1], [1, 0, 99], ["not-an-int", 0]):
            limiter = ValkeyProviderTestRateLimiter(FakeEvalClient(malformed))
            with pytest.raises(RateLimitUnavailableError):
                await limiter.check_and_consume(
                    tenant_id=TENANT_ID,
                    user_id=USER_ID,
                    provider_connection_id=CONNECTION_ID,
                )

    asyncio.run(scenario())
