from __future__ import annotations

import asyncio
from uuid import UUID

import pytest
from valkey.exceptions import ConnectionError as ValkeyConnectionError

from app.core.rate_limits import (
    KnowledgeUploadRateLimitUnavailableError,
    ValkeyKnowledgeUploadRateLimiter,
)

TENANT_ID = UUID("00000000-0000-0000-0000-000000000201")
USER_ID = UUID("00000000-0000-0000-0000-000000000202")


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


def test_knowledge_upload_limit_is_atomic_and_uses_frozen_numbers() -> None:
    async def scenario() -> None:
        client = FakeEvalClient([1, 0])
        limiter = ValkeyKnowledgeUploadRateLimiter(client)
        decision = await limiter.check_and_consume(tenant_id=TENANT_ID, user_id=USER_ID)

        assert decision.allowed is True
        assert decision.retry_after_seconds is None
        assert len(client.calls) == 1
        script, numkeys, args = client.calls[0]
        assert "GET" in script
        assert "INCR" in script
        assert "EXPIRE" in script
        assert numkeys == 1
        assert args == (
            f"serviq:rate:knowledge-upload:user:{TENANT_ID}:{USER_ID}",
            6,
            60,
        )
        assert "sk-" not in repr(args)

    asyncio.run(scenario())


def test_knowledge_upload_limit_rejection_preserves_retry_after() -> None:
    async def scenario() -> None:
        limiter = ValkeyKnowledgeUploadRateLimiter(FakeEvalClient([0, 37]))
        decision = await limiter.check_and_consume(tenant_id=TENANT_ID, user_id=USER_ID)
        assert decision.allowed is False
        assert decision.retry_after_seconds == 37

    asyncio.run(scenario())


def test_knowledge_upload_limit_store_failure_fails_closed_without_raw_detail() -> None:
    async def scenario() -> None:
        limiter = ValkeyKnowledgeUploadRateLimiter(FakeEvalClient(fail=True))
        with pytest.raises(KnowledgeUploadRateLimitUnavailableError) as captured:
            await limiter.check_and_consume(tenant_id=TENANT_ID, user_id=USER_ID)
        assert "unsafe valkey transport detail" not in str(captured.value)

    asyncio.run(scenario())


def test_knowledge_upload_limit_malformed_store_response_fails_closed() -> None:
    async def scenario() -> None:
        malformed_responses: tuple[object, ...] = (
            [],
            [1],
            [1, 0, 99],
            ["not-an-int", 0],
            None,
            1,
            "unexpected",
            {"allowed": 1},
        )
        for malformed in malformed_responses:
            limiter = ValkeyKnowledgeUploadRateLimiter(FakeEvalClient(malformed))
            with pytest.raises(KnowledgeUploadRateLimitUnavailableError):
                await limiter.check_and_consume(tenant_id=TENANT_ID, user_id=USER_ID)

    asyncio.run(scenario())
