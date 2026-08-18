"""S3-compatible object storage boundary with architecture-owned key helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import IO, Any, Protocol, cast
from uuid import UUID

import botocore.session  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

from app.core.config import PlatformSettings

_CONNECT_TIMEOUT_SECONDS = 5
_READ_TIMEOUT_SECONDS = 30
_DEFAULT_SIGNING_REGION = "us-east-1"
_NOT_FOUND_CODES = frozenset({"404", "NoSuchKey", "NotFound"})


class ObjectStorageError(RuntimeError):
    """Stable base error for object-storage failures."""

    error_code = "OBJECT_STORAGE_UNAVAILABLE"

    def __init__(self) -> None:
        super().__init__("Object storage operation failed.")


class ObjectNotFoundError(ObjectStorageError):
    """Stable object-missing error used by read operations."""

    error_code = "OBJECT_NOT_FOUND"

    def __init__(self) -> None:
        RuntimeError.__init__(self, "Object is unavailable.")


@dataclass(frozen=True, slots=True)
class KnowledgeRawObjectKey:
    tenant_id: UUID
    source_id: UUID
    object_id: UUID

    def __post_init__(self) -> None:
        _require_uuid(self.tenant_id, self.source_id, self.object_id)

    @property
    def value(self) -> str:
        return f"tenants/{self.tenant_id}/knowledge/{self.source_id}/raw/{self.object_id}"


@dataclass(frozen=True, slots=True)
class KnowledgeNormalizedObjectKey:
    tenant_id: UUID
    source_id: UUID
    document_id: UUID
    version: int

    def __post_init__(self) -> None:
        _require_uuid(self.tenant_id, self.source_id, self.document_id)
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError("Normalized object version must be a positive integer.")

    @property
    def value(self) -> str:
        return (
            f"tenants/{self.tenant_id}/knowledge/{self.source_id}/normalized/"
            f"{self.document_id}/{self.version}"
        )


@dataclass(frozen=True, slots=True)
class ExportObjectKey:
    tenant_id: UUID
    export_id: UUID

    def __post_init__(self) -> None:
        _require_uuid(self.tenant_id, self.export_id)

    @property
    def value(self) -> str:
        return f"tenants/{self.tenant_id}/exports/{self.export_id}"


@dataclass(frozen=True, slots=True)
class EvaluationObjectKey:
    tenant_id: UUID
    evaluation_run_id: UUID

    def __post_init__(self) -> None:
        _require_uuid(self.tenant_id, self.evaluation_run_id)

    @property
    def value(self) -> str:
        return f"tenants/{self.tenant_id}/evaluation/{self.evaluation_run_id}"


ObjectStorageKey = (
    KnowledgeRawObjectKey
    | KnowledgeNormalizedObjectKey
    | ExportObjectKey
    | EvaluationObjectKey
)


def knowledge_raw_key(
    *, tenant_id: UUID, source_id: UUID, object_id: UUID
) -> KnowledgeRawObjectKey:
    return KnowledgeRawObjectKey(tenant_id=tenant_id, source_id=source_id, object_id=object_id)


def knowledge_normalized_key(
    *, tenant_id: UUID, source_id: UUID, document_id: UUID, version: int
) -> KnowledgeNormalizedObjectKey:
    return KnowledgeNormalizedObjectKey(
        tenant_id=tenant_id,
        source_id=source_id,
        document_id=document_id,
        version=version,
    )


def export_key(*, tenant_id: UUID, export_id: UUID) -> ExportObjectKey:
    return ExportObjectKey(tenant_id=tenant_id, export_id=export_id)


def evaluation_key(*, tenant_id: UUID, evaluation_run_id: UUID) -> EvaluationObjectKey:
    return EvaluationObjectKey(tenant_id=tenant_id, evaluation_run_id=evaluation_run_id)


@dataclass(frozen=True, slots=True)
class StoredObject:
    data: bytes
    content_type: str | None
    content_length: int
    etag: str | None


class ObjectStorage(Protocol):
    def put_object(
        self,
        key: ObjectStorageKey,
        data: bytes | IO[bytes],
        *,
        content_type: str,
    ) -> None: ...

    def get_object(self, key: ObjectStorageKey) -> StoredObject: ...

    def delete_object(self, key: ObjectStorageKey) -> None: ...

    def exists(self, key: ObjectStorageKey) -> bool: ...


class _S3Client(Protocol):
    def put_object(self, **kwargs: Any) -> dict[str, Any]: ...

    def get_object(self, **kwargs: Any) -> dict[str, Any]: ...

    def delete_object(self, **kwargs: Any) -> dict[str, Any]: ...

    def head_object(self, **kwargs: Any) -> dict[str, Any]: ...


class _S3Session(Protocol):
    def create_client(self, service_name: str, **kwargs: Any) -> _S3Client: ...


class S3ObjectStorage:
    """Small S3-compatible adapter for the four operations Serviq currently owns."""

    def __init__(self, *, client: _S3Client, bucket: str) -> None:
        normalized_bucket = bucket.strip()
        if not normalized_bucket:
            raise ValueError("Object storage bucket must not be blank.")
        self._client = client
        self._bucket = normalized_bucket

    def __repr__(self) -> str:
        return "<S3ObjectStorage redacted>"

    def put_object(
        self,
        key: ObjectStorageKey,
        data: bytes | IO[bytes],
        *,
        content_type: str,
    ) -> None:
        normalized_content_type = content_type.strip()
        if not normalized_content_type:
            raise ValueError("Object content type must not be blank.")
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key.value,
                Body=data,
                ContentType=normalized_content_type,
            )
        except (BotoCoreError, ClientError):
            raise ObjectStorageError from None

    def get_object(self, key: ObjectStorageKey) -> StoredObject:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key.value)
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

        content_type = response.get("ContentType")
        if not isinstance(content_type, str):
            content_type = None
        content_length = response.get("ContentLength")
        if not isinstance(content_length, int):
            content_length = len(data)
        etag = response.get("ETag")
        if not isinstance(etag, str):
            etag = None

        return StoredObject(
            data=data,
            content_type=content_type,
            content_length=content_length,
            etag=etag,
        )

    def delete_object(self, key: ObjectStorageKey) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key.value)
        except ClientError as exc:
            if _is_not_found(exc):
                return
            raise ObjectStorageError from None
        except BotoCoreError:
            raise ObjectStorageError from None

    def exists(self, key: ObjectStorageKey) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key.value)
        except ClientError as exc:
            if _is_not_found(exc):
                return False
            raise ObjectStorageError from None
        except BotoCoreError:
            raise ObjectStorageError from None
        return True


def build_object_storage(
    settings: PlatformSettings,
    *,
    session: _S3Session | None = None,
) -> S3ObjectStorage:
    """Build the architecture-owned adapter from environment-backed platform settings."""

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

    return S3ObjectStorage(client=client, bucket=settings.object_storage_bucket)


def _require_uuid(*values: object) -> None:
    if any(not isinstance(value, UUID) for value in values):
        raise TypeError("Object key identifiers must be UUID values.")


def _is_not_found(exc: ClientError) -> bool:
    error = exc.response.get("Error")
    code: str | None = None
    if isinstance(error, dict):
        raw_code = error.get("Code")
        if isinstance(raw_code, str):
            code = raw_code
    if code is not None:
        return code in _NOT_FOUND_CODES

    response_metadata = exc.response.get("ResponseMetadata")
    if isinstance(response_metadata, dict):
        return response_metadata.get("HTTPStatusCode") == 404
    return False
