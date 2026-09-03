"""Small S3-compatible raw-object boundary for durable worker jobs."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol, cast

import botocore.session  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

from app.core.config import PlatformSettings

_CONNECT_TIMEOUT_SECONDS = 5
_READ_TIMEOUT_SECONDS = 30
_DEFAULT_SIGNING_REGION = "us-east-1"
_NOT_FOUND_CODES = frozenset({"404", "NoSuchKey", "NotFound"})


class ObjectStorageError(RuntimeError):
    """Safe storage failure that never exposes provider details."""


class ObjectNotFoundError(ObjectStorageError):
    """Safe missing-object failure."""


class _S3Client(Protocol):
    def put_object(self, **kwargs: Any) -> dict[str, Any]: ...

    def get_object(self, **kwargs: Any) -> dict[str, Any]: ...


class _S3Session(Protocol):
    def create_client(self, service_name: str, **kwargs: Any) -> _S3Client: ...


class S3RawObjectStorage:
    """Worker-owned adapter for already-validated tenant-scoped raw keys."""

    def __init__(self, *, client: _S3Client, bucket: str) -> None:
        normalized_bucket = bucket.strip()
        if not normalized_bucket:
            raise ValueError("Object storage bucket must not be blank.")
        self._client = client
        self._bucket = normalized_bucket

    async def put_bytes(self, key: str, data: bytes, *, content_type: str) -> None:
        await asyncio.to_thread(self._put_bytes_sync, key, data, content_type)

    def _put_bytes_sync(self, key: str, data: bytes, content_type: str) -> None:
        _validate_key(key)
        normalized_content_type = content_type.strip()
        if not normalized_content_type:
            raise ValueError("Object content type must not be blank.")
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=normalized_content_type,
            )
        except (BotoCoreError, ClientError):
            raise ObjectStorageError from None

    async def get_bytes(self, key: str) -> bytes:
        return await asyncio.to_thread(self._get_bytes_sync, key)

    def _get_bytes_sync(self, key: str) -> bytes:
        _validate_key(key)
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if _is_not_found(exc):
                raise ObjectNotFoundError from None
            raise ObjectStorageError from None
        except BotoCoreError:
            raise ObjectStorageError from None

        body = response.get("Body")
        if body is None or not hasattr(body, "read"):
            raise ObjectStorageError
        try:
            data = body.read()
        except Exception:
            raise ObjectStorageError from None
        finally:
            close = getattr(body, "close", None)
            if callable(close):
                close()
        if not isinstance(data, bytes):
            raise ObjectStorageError
        return data


def build_object_storage(
    settings: PlatformSettings,
    *,
    session: _S3Session | None = None,
) -> S3RawObjectStorage:
    """Build the worker S3-compatible adapter from frozen platform settings."""

    storage_session = session
    if storage_session is None:
        storage_session = cast(_S3Session, botocore.session.get_session())

    access_key = settings.object_storage_access_key.get_secret_value()
    secret_key = settings.object_storage_secret_key.get_secret_value()
    try:
        client = storage_session.create_client(
            "s3",
            endpoint_url=str(settings.object_storage_endpoint).rstrip("/"),
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=_DEFAULT_SIGNING_REGION,
            config=Config(
                signature_version="s3v4",
                connect_timeout=_CONNECT_TIMEOUT_SECONDS,
                read_timeout=_READ_TIMEOUT_SECONDS,
                retries={"mode": "standard", "total_max_attempts": 1},
                s3={"addressing_style": "path"},
            ),
        )
    except BotoCoreError:
        raise ObjectStorageError from None
    finally:
        del access_key
        del secret_key

    return S3RawObjectStorage(client=client, bucket=settings.object_storage_bucket)


def _validate_key(key: str) -> None:
    if not isinstance(key, str) or not key or key.startswith("/"):
        raise ValueError("Object storage key must be a non-empty relative key.")
    if "\0" in key or "\r" in key or "\n" in key:
        raise ValueError("Object storage key contains unsupported control characters.")


def _is_not_found(exc: ClientError) -> bool:
    error = exc.response.get("Error")
    if isinstance(error, dict):
        code = error.get("Code")
        if isinstance(code, str):
            return code in _NOT_FOUND_CODES
    metadata = exc.response.get("ResponseMetadata")
    return isinstance(metadata, dict) and metadata.get("HTTPStatusCode") == 404
