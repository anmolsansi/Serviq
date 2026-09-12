from __future__ import annotations

import asyncio
from io import BytesIO
from typing import Any

import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from app.core.object_storage import ObjectStorageError, S3RawObjectStorage


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail_head = False
        self.fail_delete = False

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.objects[str(kwargs["Key"])] = bytes(kwargs["Body"])
        return {}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        object_path = str(kwargs["Key"])
        if object_path not in self.objects:
            raise _client_error("NoSuchKey", 404, "GetObject")
        return {"Body": BytesIO(self.objects[object_path])}

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        if self.fail_head:
            raise _client_error("InternalError", 500, "HeadObject")
        object_path = str(kwargs["Key"])
        if object_path not in self.objects:
            raise _client_error("NoSuchKey", 404, "HeadObject")
        return {"ContentLength": len(self.objects[object_path])}

    def delete_object(self, **kwargs: Any) -> dict[str, Any]:
        if self.fail_delete:
            raise _client_error("InternalError", 500, "DeleteObject")
        self.objects.pop(str(kwargs["Key"]), None)
        return {}


def _client_error(code: str, status: int, operation: str) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": "synthetic"},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        operation,
    )


def test_exists_reports_visible_and_missing_objects() -> None:
    client = FakeS3Client()
    client.objects["tenants/t/knowledge/s/raw/o"] = b"payload"
    storage = S3RawObjectStorage(client=client, bucket="bucket")

    assert asyncio.run(storage.exists("tenants/t/knowledge/s/raw/o")) is True
    assert asyncio.run(storage.exists("tenants/t/knowledge/s/raw/missing")) is False


def test_exists_maps_provider_failure_to_safe_error() -> None:
    client = FakeS3Client()
    client.fail_head = True
    storage = S3RawObjectStorage(client=client, bucket="bucket")

    with pytest.raises(ObjectStorageError):
        asyncio.run(storage.exists("tenants/t/knowledge/s/raw/o"))


def test_delete_is_idempotent_and_maps_provider_failure() -> None:
    object_path = "tenants/t/knowledge/s/raw/o"
    client = FakeS3Client()
    client.objects[object_path] = b"payload"
    storage = S3RawObjectStorage(client=client, bucket="bucket")

    asyncio.run(storage.delete_object(object_path))
    asyncio.run(storage.delete_object(object_path))
    assert object_path not in client.objects

    client.fail_delete = True
    with pytest.raises(ObjectStorageError):
        asyncio.run(storage.delete_object(object_path))


def test_cleanup_storage_operations_reject_untrusted_keys() -> None:
    storage = S3RawObjectStorage(client=FakeS3Client(), bucket="bucket")

    with pytest.raises(ValueError, match="relative key"):
        asyncio.run(storage.exists("/absolute"))
    with pytest.raises(ValueError, match="control characters"):
        asyncio.run(storage.delete_object("bad\nkey"))
