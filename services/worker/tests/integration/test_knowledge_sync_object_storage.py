from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest

from app.core.config import load_settings
from app.core.object_storage import build_object_storage

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_OBJECT_STORAGE_INTEGRATION") != "1",
    reason="requires the real local S3-compatible object storage environment",
)


def test_worker_s3_put_and_get_round_trip() -> None:
    async def scenario() -> None:
        storage = build_object_storage(load_settings())
        tenant_id = uuid4()
        source_id = uuid4()
        key = f"tenants/{tenant_id}/knowledge/{source_id}/sync/1/raw"
        payload = b"Serviq OPE-313 worker object storage integration"

        await storage.put_bytes(key, payload, content_type="text/plain")
        stored = await storage.get_bytes(key)

        assert stored == payload

    asyncio.run(scenario())
