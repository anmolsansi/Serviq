from __future__ import annotations

import asyncio
import os
from uuid import UUID

import pytest
import valkey.asyncio as valkey

from app.core.config import load_settings
from app.core.rate_limits import build_knowledge_upload_rate_limiter

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_VALKEY_INTEGRATION") != "1",
    reason="requires the real Valkey integration environment",
)

TENANT_ID = UUID("00000000-0000-0000-0000-000000000401")
OTHER_TENANT_ID = UUID("00000000-0000-0000-0000-000000000402")
USER_ID = UUID("00000000-0000-0000-0000-000000000403")


def _normalized_valkey_url() -> str:
    raw = str(load_settings().valkey_url)
    return raw.replace("valkey://", "redis://", 1) if raw.startswith("valkey://") else raw


def test_real_valkey_enforces_six_upload_attempts_per_minute_and_tenant_isolation() -> None:
    async def scenario() -> None:
        client = valkey.from_url(_normalized_valkey_url(), decode_responses=False)
        try:
            await client.flushdb()
            limiter = build_knowledge_upload_rate_limiter(load_settings())
            for _ in range(6):
                decision = await limiter.check_and_consume(tenant_id=TENANT_ID, user_id=USER_ID)
                assert decision.allowed is True
                assert decision.retry_after_seconds is None

            rejected = await limiter.check_and_consume(tenant_id=TENANT_ID, user_id=USER_ID)
            assert rejected.allowed is False
            assert rejected.retry_after_seconds is not None
            assert 1 <= rejected.retry_after_seconds <= 60

            foreign_tenant = await limiter.check_and_consume(
                tenant_id=OTHER_TENANT_ID,
                user_id=USER_ID,
            )
            assert foreign_tenant.allowed is True
        finally:
            await client.aclose()

    asyncio.run(scenario())
