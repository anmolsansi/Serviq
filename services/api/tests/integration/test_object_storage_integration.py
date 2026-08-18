from __future__ import annotations

import os
from uuid import UUID

import pytest

from app.core.config import load_settings
from app.core.object_storage import build_object_storage, knowledge_raw_key

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_OBJECT_STORAGE_INTEGRATION") != "1",
    reason="requires the real local S3-compatible object storage environment",
)

TENANT_ID = UUID("00000000-0000-0000-0000-000000000301")
SOURCE_ID = UUID("10000000-0000-0000-0000-000000000301")
OBJECT_ID = UUID("20000000-0000-0000-0000-000000000301")


def test_local_s3_put_get_head_exists_and_idempotent_delete_round_trip() -> None:
    storage = build_object_storage(load_settings())
    key = knowledge_raw_key(
        tenant_id=TENANT_ID,
        source_id=SOURCE_ID,
        object_id=OBJECT_ID,
    )
    payload = b"Serviq OPE-301 local object-storage round trip"
    filename = "../../customer-contract.pdf"

    storage.delete_object(key)
    assert storage.exists(key) is False

    try:
        storage.put_object(
            key,
            payload,
            content_type="text/plain",
            metadata={"original-filename": filename},
        )
        assert storage.exists(key) is True
        assert filename not in key.value

        head = storage.head(key)
        assert head.content_type == "text/plain"
        assert head.content_length == len(payload)
        assert head.metadata.get("original-filename") == filename

        stored = storage.get_object(key)
        assert stored.data == payload
        assert stored.content_type == "text/plain"
        assert stored.content_length == len(payload)
        assert stored.metadata.get("original-filename") == filename
    finally:
        storage.delete_object(key)

    assert storage.exists(key) is False
    storage.delete_object(key)
