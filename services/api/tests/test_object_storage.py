from __future__ import annotations

from io import BytesIO
from typing import Any, cast
from uuid import UUID

import pytest
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from app.core.config import PlatformSettings, load_settings
from app.core.object_storage import (
    ObjectNotFoundError,
    ObjectStorageError,
    S3ObjectStorage,
    build_object_storage,
    evaluation_key,
    export_key,
    knowledge_normalized_key,
    knowledge_raw_key,
)

TENANT_ID = UUID("00000000-0000-0000-0000-000000000301")
OTHER_TENANT_ID = UUID("00000000-0000-0000-0000-000000000302")
SOURCE_ID = UUID("10000000-0000-0000-0000-000000000301")
OBJECT_ID = UUID("20000000-0000-0000-0000-000000000301")
DOCUMENT_ID = UUID("30000000-0000-0000-0000-000000000301")
EXPORT_ID = UUID("40000000-0000-0000-0000-000000000301")
EVALUATION_RUN_ID = UUID("50000000-0000-0000-0000-000000000301")
SECRET = "storage-secret-never-real"
UNSAFE_DETAIL = f"http://internal-storage.invalid credential={SECRET}"


class _FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str, dict[str, str]]] = {}
        self.fail = False
        self.fail_missing_bucket = False
        self.calls: list[tuple[str, str, str]] = []

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        bucket = cast(str, kwargs["Bucket"])
        key = cast(str, kwargs["Key"])
        body = kwargs["Body"]
        content_type = cast(str, kwargs["ContentType"])
        metadata = cast(dict[str, str], kwargs["Metadata"])
        if self.fail:
            raise _unsafe_client_error("PutObject")
        data = body if isinstance(body, bytes) else cast(BytesIO, body).read()
        self.objects[(bucket, key)] = (data, content_type, dict(metadata))
        self.calls.append(("put", bucket, key))
        return {"ETag": "test-etag"}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        bucket = cast(str, kwargs["Bucket"])
        key = cast(str, kwargs["Key"])
        if self.fail:
            raise _unsafe_client_error("GetObject")
        stored = self.objects.get((bucket, key))
        if stored is None:
            raise _missing_client_error("GetObject")
        data, content_type, metadata = stored
        self.calls.append(("get", bucket, key))
        return {
            "Body": BytesIO(data),
            "ContentType": content_type,
            "ContentLength": len(data),
            "ETag": "test-etag",
            "Metadata": dict(metadata),
        }

    def delete_object(self, **kwargs: Any) -> dict[str, Any]:
        bucket = cast(str, kwargs["Bucket"])
        key = cast(str, kwargs["Key"])
        if self.fail:
            raise _unsafe_client_error("DeleteObject")
        self.objects.pop((bucket, key), None)
        self.calls.append(("delete", bucket, key))
        return {}

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        bucket = cast(str, kwargs["Bucket"])
        key = cast(str, kwargs["Key"])
        if self.fail:
            raise _unsafe_client_error("HeadObject")
        if self.fail_missing_bucket:
            raise _missing_bucket_client_error("HeadObject")
        stored = self.objects.get((bucket, key))
        if stored is None:
            raise _missing_client_error("HeadObject")
        data, content_type, metadata = stored
        self.calls.append(("head", bucket, key))
        return {
            "ContentLength": len(data),
            "ContentType": content_type,
            "ETag": "test-etag",
            "Metadata": dict(metadata),
        }


class _FakeS3Session:
    def __init__(self, client: _FakeS3Client) -> None:
        self.client = client
        self.service_name: str | None = None
        self.kwargs: dict[str, Any] = {}

    def create_client(self, service_name: str, **kwargs: Any) -> _FakeS3Client:
        self.service_name = service_name
        self.kwargs = kwargs
        return self.client


def _settings(
    *,
    endpoint: str = "http://object-storage.internal:8333",
    bucket: str = "serviq-unit-objects",
) -> PlatformSettings:
    return load_settings(
        {
            "SERVIQ_ENV": "test",
            "SERVIQ_PUBLIC_BASE_URL": "http://localhost:3000",
            "SERVIQ_API_BASE_URL": "http://localhost:8000",
            "DATABASE_URL": "postgresql://serviq:test@localhost:5432/serviq",
            "VALKEY_URL": "valkey://localhost:6379/0",
            "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
            "OBJECT_STORAGE_ENDPOINT": endpoint,
            "OBJECT_STORAGE_BUCKET": bucket,
            "OBJECT_STORAGE_ACCESS_KEY": "unit-access",
            "OBJECT_STORAGE_SECRET_KEY": SECRET,
            "OIDC_ISSUER_URL": "http://localhost:8080/realms/serviq",
            "OIDC_CLIENT_ID": "serviq-test",
            "OIDC_CLIENT_SECRET": "test-oidc",
            "OIDC_REDIRECT_URI": "http://localhost:3000/auth/callback",
            "SESSION_SECRET": "test-session",
            "LLM_GATEWAY_URL": "http://llm-gateway.internal:8100",
            "LLM_GATEWAY_INTERNAL_TOKEN": "test-internal-token",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
            "LOG_LEVEL": "INFO",
            "SERVIQ_LOCAL_WEBHOOK_ALLOWLIST": "",
        }
    )


def test_object_key_helpers_match_frozen_layouts_exactly() -> None:
    assert knowledge_raw_key(
        tenant_id=TENANT_ID,
        source_id=SOURCE_ID,
        object_id=OBJECT_ID,
    ).value == f"tenants/{TENANT_ID}/knowledge/{SOURCE_ID}/raw/{OBJECT_ID}"
    assert knowledge_normalized_key(
        tenant_id=TENANT_ID,
        source_id=SOURCE_ID,
        document_id=DOCUMENT_ID,
        version=7,
    ).value == (
        f"tenants/{TENANT_ID}/knowledge/{SOURCE_ID}/normalized/{DOCUMENT_ID}/7"
    )
    assert export_key(
        tenant_id=TENANT_ID,
        export_id=EXPORT_ID,
    ).value == f"tenants/{TENANT_ID}/exports/{EXPORT_ID}"
    assert evaluation_key(
        tenant_id=TENANT_ID,
        evaluation_run_id=EVALUATION_RUN_ID,
    ).value == f"tenants/{TENANT_ID}/evaluation/{EVALUATION_RUN_ID}"


def test_keys_are_tenant_scoped_and_do_not_accept_user_paths() -> None:
    first = knowledge_raw_key(
        tenant_id=TENANT_ID,
        source_id=SOURCE_ID,
        object_id=OBJECT_ID,
    )
    second = knowledge_raw_key(
        tenant_id=OTHER_TENANT_ID,
        source_id=SOURCE_ID,
        object_id=OBJECT_ID,
    )

    assert first.value.startswith(f"tenants/{TENANT_ID}/")
    assert second.value.startswith(f"tenants/{OTHER_TENANT_ID}/")
    assert first.value != second.value

    with pytest.raises(TypeError):
        knowledge_raw_key(
            tenant_id=cast(Any, "../../another-tenant"),
            source_id=SOURCE_ID,
            object_id=OBJECT_ID,
        )


@pytest.mark.parametrize(
    "filename",
    [
        "../../secret",
        "folder/private.pdf",
        "folder\\private.pdf",
        "customer\u2028private.pdf",
        "x" * 4096 + ".pdf",
    ],
)
def test_user_filename_can_be_metadata_but_never_changes_generated_key(filename: str) -> None:
    client = _FakeS3Client()
    storage = S3ObjectStorage(client=client, bucket="configured-bucket")
    key = knowledge_raw_key(tenant_id=TENANT_ID, source_id=SOURCE_ID, object_id=OBJECT_ID)
    expected_key = f"tenants/{TENANT_ID}/knowledge/{SOURCE_ID}/raw/{OBJECT_ID}"

    storage.put_object(
        key,
        b"content",
        content_type="application/pdf",
        metadata={"original-filename": filename},
    )

    assert key.value == expected_key
    assert filename not in key.value
    assert client.calls[-1] == ("put", "configured-bucket", expected_key)
    _, _, stored_metadata = client.objects[("configured-bucket", expected_key)]
    assert stored_metadata == {"original-filename": filename}


def test_normalized_key_requires_positive_integer_version() -> None:
    with pytest.raises(ValueError):
        knowledge_normalized_key(
            tenant_id=TENANT_ID,
            source_id=SOURCE_ID,
            document_id=DOCUMENT_ID,
            version=0,
        )


def test_put_get_head_exists_delete_and_repeated_delete_are_safe() -> None:
    client = _FakeS3Client()
    storage = S3ObjectStorage(client=client, bucket="configured-bucket")
    key = knowledge_raw_key(tenant_id=TENANT_ID, source_id=SOURCE_ID, object_id=OBJECT_ID)

    assert storage.exists(key) is False
    storage.put_object(
        key,
        BytesIO(b"hello storage"),
        content_type="text/plain",
        metadata={"source": "unit-test"},
    )
    assert storage.exists(key) is True

    head = storage.head(key)
    assert head.content_type == "text/plain"
    assert head.content_length == len(b"hello storage")
    assert head.etag == "test-etag"
    assert head.metadata == {"source": "unit-test"}

    stored = storage.get_object(key)
    assert stored.data == b"hello storage"
    assert stored.content_type == "text/plain"
    assert stored.content_length == len(b"hello storage")
    assert stored.etag == "test-etag"
    assert stored.metadata == {"source": "unit-test"}
    assert ("put", "configured-bucket", key.value) in client.calls
    assert ("head", "configured-bucket", key.value) in client.calls

    storage.delete_object(key)
    assert storage.exists(key) is False
    storage.delete_object(key)


def test_missing_get_and_head_are_normalized() -> None:
    storage = S3ObjectStorage(client=_FakeS3Client(), bucket="configured-bucket")
    key = export_key(tenant_id=TENANT_ID, export_id=EXPORT_ID)

    with pytest.raises(ObjectNotFoundError) as get_error:
        storage.get_object(key)
    with pytest.raises(ObjectNotFoundError) as head_error:
        storage.head(key)

    assert get_error.value.error_code == "OBJECT_NOT_FOUND"
    assert head_error.value.error_code == "OBJECT_NOT_FOUND"
    assert UNSAFE_DETAIL not in repr(get_error.value)
    assert UNSAFE_DETAIL not in repr(head_error.value)


def test_missing_bucket_is_not_misreported_as_a_missing_object() -> None:
    client = _FakeS3Client()
    client.fail_missing_bucket = True
    storage = S3ObjectStorage(client=client, bucket="missing-bucket")
    key = export_key(tenant_id=TENANT_ID, export_id=EXPORT_ID)

    with pytest.raises(ObjectStorageError) as caught:
        storage.exists(key)

    assert caught.value.error_code == "OBJECT_STORAGE_UNAVAILABLE"
    assert "missing-bucket" not in repr(caught.value)


def test_backend_failures_do_not_leak_sdk_details_or_credentials() -> None:
    client = _FakeS3Client()
    client.fail = True
    storage = S3ObjectStorage(client=client, bucket="configured-bucket")
    key = evaluation_key(tenant_id=TENANT_ID, evaluation_run_id=EVALUATION_RUN_ID)

    with pytest.raises(ObjectStorageError) as caught:
        storage.exists(key)

    rendered = f"{caught.value!r} {caught.value}"
    assert caught.value.error_code == "OBJECT_STORAGE_UNAVAILABLE"
    assert SECRET not in rendered
    assert "internal-storage.invalid" not in rendered
    assert UNSAFE_DETAIL not in rendered


def test_metadata_rejects_control_characters() -> None:
    storage = S3ObjectStorage(client=_FakeS3Client(), bucket="configured-bucket")
    key = export_key(tenant_id=TENANT_ID, export_id=EXPORT_ID)

    with pytest.raises(ValueError):
        storage.put_object(
            key,
            b"export",
            content_type="application/octet-stream",
            metadata={"original-filename": "unsafe\r\nheader.pdf"},
        )


def test_factory_uses_configurable_endpoint_bucket_timeouts_and_bounded_retries() -> None:
    client = _FakeS3Client()
    session = _FakeS3Session(client)
    storage = build_object_storage(
        _settings(endpoint="http://storage.example:9444", bucket="tenant-objects"),
        session=session,
    )
    key = export_key(tenant_id=TENANT_ID, export_id=EXPORT_ID)

    storage.put_object(key, b"export", content_type="application/octet-stream")

    assert session.service_name == "s3"
    assert session.kwargs["endpoint_url"] == "http://storage.example:9444"
    assert client.calls[-1] == ("put", "tenant-objects", key.value)
    config = cast(Config, session.kwargs["config"])
    assert config.connect_timeout == 5
    assert config.read_timeout == 30
    assert config.retries == {"mode": "standard", "total_max_attempts": 1}
    assert config.signature_version == "s3v4"
    assert config.s3 == {"addressing_style": "path"}
    assert "unit-access" not in repr(storage)
    assert SECRET not in repr(storage)


def _missing_client_error(operation: str) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": "NoSuchKey", "Message": UNSAFE_DETAIL},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        },
        operation,
    )


def _missing_bucket_client_error(operation: str) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": "NoSuchBucket", "Message": "missing-bucket"},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        },
        operation,
    )


def _unsafe_client_error(operation: str) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": "InternalError", "Message": UNSAFE_DETAIL},
            "ResponseMetadata": {"HTTPStatusCode": 500},
        },
        operation,
    )
