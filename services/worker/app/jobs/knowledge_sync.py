"""Idempotent knowledge-source fetch and durable parse-handoff job."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.object_storage import ObjectNotFoundError, ObjectStorageError, S3RawObjectStorage
from app.core.public_knowledge_fetch import (
    PublicKnowledgeFetchError,
    PublicKnowledgeFetchPolicy,
    fetch_public_knowledge,
)

SYNC_EVENT_TYPE = "serviq.knowledge.sync.v1"
PARSE_EVENT_TYPE = "serviq.knowledge.parse.v1"
PARSE_SCHEMA_VERSION = 1


class KnowledgeSyncErrorCode(StrEnum):
    SOURCE_NOT_FOUND = "KNOWLEDGE_SYNC_SOURCE_NOT_FOUND"
    SOURCE_DISABLED = "KNOWLEDGE_SOURCE_DISABLED"
    VERSION_AHEAD = "KNOWLEDGE_SYNC_VERSION_AHEAD"
    SOURCE_TYPE_UNSUPPORTED = "KNOWLEDGE_SYNC_SOURCE_TYPE_UNSUPPORTED"
    OBJECT_UNAVAILABLE = "KNOWLEDGE_SOURCE_OBJECT_UNAVAILABLE"
    REPLAY_CONTENT_MISMATCH = "KNOWLEDGE_SYNC_REPLAY_CONTENT_MISMATCH"


@dataclass(frozen=True, slots=True)
class KnowledgeSyncCommand:
    event_id: UUID
    tenant_id: UUID
    source_id: UUID
    sync_version: int
    correlation_id: str


@dataclass(frozen=True, slots=True)
class KnowledgeSyncResult:
    completed: bool
    noop: bool = False
    error_code: str | None = None
    retryable: bool = False

    @classmethod
    def success(cls) -> KnowledgeSyncResult:
        return cls(completed=True)

    @classmethod
    def no_op(cls) -> KnowledgeSyncResult:
        return cls(completed=True, noop=True)

    @classmethod
    def failure(cls, code: str, *, retryable: bool) -> KnowledgeSyncResult:
        return cls(completed=False, error_code=code, retryable=retryable)


@dataclass(frozen=True, slots=True)
class _SourceSnapshot:
    source_type: str
    name: str
    source_uri: str | None
    object_key: str | None
    status: str
    sync_version: int


@dataclass(frozen=True, slots=True)
class _FetchedContent:
    raw_bytes: bytes
    raw_object_key: str
    canonical_uri: str | None
    content_type: str


_SOURCE_SELECT = text(
    """
    SELECT source_type, name, source_uri, object_key, status, sync_version
    FROM knowledge_sources
    WHERE id = :source_id AND tenant_id = :tenant_id
    """
)
_SOURCE_LOCK = text(
    """
    SELECT source_type, name, source_uri, object_key, status, sync_version
    FROM knowledge_sources
    WHERE id = :source_id AND tenant_id = :tenant_id
    FOR UPDATE
    """
)
_DOCUMENT_BY_VERSION = text(
    """
    SELECT id, content_hash
    FROM knowledge_documents
    WHERE tenant_id = :tenant_id
      AND source_id = :source_id
      AND document_version = :document_version
    ORDER BY created_at ASC
    LIMIT 1
    """
)
_DOCUMENT_INSERT = text(
    """
    INSERT INTO knowledge_documents (
        tenant_id, source_id, canonical_uri, title, content_hash,
        document_version, status, fetched_at, created_at, updated_at
    ) VALUES (
        :tenant_id, :source_id, :canonical_uri, :title, :content_hash,
        :document_version, 'active', now(), now(), now()
    )
    RETURNING id
    """
)
_PARSE_EVENT_EXISTS = text(
    """
    SELECT 1
    FROM outbox_events
    WHERE tenant_id = :tenant_id
      AND event_type = :event_type
      AND aggregate_type = 'knowledge_document'
      AND aggregate_id = :aggregate_id
    LIMIT 1
    """
)
_PARSE_EVENT_INSERT = text(
    """
    INSERT INTO outbox_events (
        tenant_id, event_type, schema_version, aggregate_type, aggregate_id,
        payload, correlation_id, causation_id, status, attempts, next_attempt_at
    ) VALUES (
        :tenant_id, :event_type, :schema_version, 'knowledge_document', :aggregate_id,
        CAST(:payload AS jsonb), :correlation_id, :causation_id, 'pending', 0, now()
    )
    """
)
_SOURCE_SUCCESS_UPDATE = text(
    """
    UPDATE knowledge_sources
    SET status = 'syncing', last_synced_at = now(), last_error_code = NULL, updated_at = now()
    WHERE id = :source_id AND tenant_id = :tenant_id AND sync_version = :sync_version
    """
)
_SOURCE_FAILURE_UPDATE = text(
    """
    UPDATE knowledge_sources
    SET status = 'failed', last_error_code = :error_code, updated_at = now()
    WHERE id = :source_id
      AND tenant_id = :tenant_id
      AND sync_version = :sync_version
      AND status <> 'disabled'
    """
)


async def run_knowledge_sync(
    session_factory: async_sessionmaker[AsyncSession],
    storage: S3RawObjectStorage,
    command: KnowledgeSyncCommand,
) -> KnowledgeSyncResult:
    """Fetch one source version and atomically persist document + parse obligation."""

    source = await _load_source(session_factory, command)
    if source is None:
        return KnowledgeSyncResult.failure(KnowledgeSyncErrorCode.SOURCE_NOT_FOUND, retryable=False)
    if source.status == "disabled":
        return KnowledgeSyncResult.failure(KnowledgeSyncErrorCode.SOURCE_DISABLED, retryable=False)
    if command.sync_version < source.sync_version:
        return KnowledgeSyncResult.no_op()
    if command.sync_version > source.sync_version:
        return KnowledgeSyncResult.failure(KnowledgeSyncErrorCode.VERSION_AHEAD, retryable=False)
    if source.source_type == "sitemap":
        return KnowledgeSyncResult.failure(
            KnowledgeSyncErrorCode.SOURCE_TYPE_UNSUPPORTED,
            retryable=False,
        )

    fetched = await _fetch_content(storage, command, source)
    if isinstance(fetched, KnowledgeSyncResult):
        return fetched

    content_hash = hashlib.sha256(fetched.raw_bytes).hexdigest()
    existing = await _load_existing_document(session_factory, command, content_hash)
    if existing is not None:
        return existing

    if source.source_type == "url":
        try:
            await storage.put_bytes(
                fetched.raw_object_key,
                fetched.raw_bytes,
                content_type=fetched.content_type,
            )
        except ObjectStorageError:
            return KnowledgeSyncResult.failure(
                KnowledgeSyncErrorCode.OBJECT_UNAVAILABLE,
                retryable=True,
            )

    return await _persist_document_and_parse_event(
        session_factory,
        command,
        source,
        fetched,
        content_hash,
    )


async def mark_matching_source_failed(
    session_factory: async_sessionmaker[AsyncSession],
    command: KnowledgeSyncCommand,
    error_code: str,
) -> None:
    """Persist a safe failure only when the event still owns the source version."""

    async with session_factory() as session:
        async with session.begin():
            await session.execute(
                _SOURCE_FAILURE_UPDATE,
                {
                    "source_id": command.source_id,
                    "tenant_id": command.tenant_id,
                    "sync_version": command.sync_version,
                    "error_code": error_code,
                },
            )


async def _load_source(
    session_factory: async_sessionmaker[AsyncSession],
    command: KnowledgeSyncCommand,
) -> _SourceSnapshot | None:
    async with session_factory() as session:
        result = await session.execute(
            _SOURCE_SELECT,
            {"source_id": command.source_id, "tenant_id": command.tenant_id},
        )
        row = result.mappings().one_or_none()
    return None if row is None else _snapshot_from_row(row)


async def _load_existing_document(
    session_factory: async_sessionmaker[AsyncSession],
    command: KnowledgeSyncCommand,
    content_hash: str,
) -> KnowledgeSyncResult | None:
    async with session_factory() as session:
        result = await session.execute(
            _DOCUMENT_BY_VERSION,
            {
                "tenant_id": command.tenant_id,
                "source_id": command.source_id,
                "document_version": command.sync_version,
            },
        )
        row = result.mappings().one_or_none()
    if row is None:
        return None
    existing_hash = row.get("content_hash")
    if existing_hash != content_hash:
        return KnowledgeSyncResult.failure(
            KnowledgeSyncErrorCode.REPLAY_CONTENT_MISMATCH,
            retryable=False,
        )
    return KnowledgeSyncResult.no_op()


async def _fetch_content(
    storage: S3RawObjectStorage,
    command: KnowledgeSyncCommand,
    source: _SourceSnapshot,
) -> _FetchedContent | KnowledgeSyncResult:
    if source.source_type == "url":
        source_uri = source.source_uri
        if source_uri is None:
            return KnowledgeSyncResult.failure(KnowledgeSyncErrorCode.SOURCE_NOT_FOUND, retryable=False)
        host = urlsplit(source_uri).hostname
        if host is None:
            return KnowledgeSyncResult.failure(KnowledgeSyncErrorCode.SOURCE_NOT_FOUND, retryable=False)
        try:
            result = await asyncio.to_thread(
                fetch_public_knowledge,
                source_uri,
                PublicKnowledgeFetchPolicy(allowed_hosts=frozenset({host})),
            )
        except PublicKnowledgeFetchError as error:
            return KnowledgeSyncResult.failure(error.code.value, retryable=error.retryable)
        return _FetchedContent(
            raw_bytes=result.body,
            raw_object_key=_sync_raw_key(command),
            canonical_uri=result.final_url,
            content_type=result.content_type,
        )

    if source.source_type not in {"pdf", "markdown", "text"}:
        return KnowledgeSyncResult.failure(
            KnowledgeSyncErrorCode.SOURCE_TYPE_UNSUPPORTED,
            retryable=False,
        )
    object_key = source.object_key
    if object_key is None or not _is_tenant_source_key(object_key, command):
        return KnowledgeSyncResult.failure(KnowledgeSyncErrorCode.SOURCE_NOT_FOUND, retryable=False)
    try:
        raw_bytes = await storage.get_bytes(object_key)
    except (ObjectNotFoundError, ObjectStorageError):
        return KnowledgeSyncResult.failure(
            KnowledgeSyncErrorCode.OBJECT_UNAVAILABLE,
            retryable=True,
        )
    return _FetchedContent(
        raw_bytes=raw_bytes,
        raw_object_key=object_key,
        canonical_uri=None,
        content_type=_file_content_type(source.source_type),
    )


async def _persist_document_and_parse_event(
    session_factory: async_sessionmaker[AsyncSession],
    command: KnowledgeSyncCommand,
    source: _SourceSnapshot,
    fetched: _FetchedContent,
    content_hash: str,
) -> KnowledgeSyncResult:
    async with session_factory() as session:
        async with session.begin():
            locked_result = await session.execute(
                _SOURCE_LOCK,
                {"source_id": command.source_id, "tenant_id": command.tenant_id},
            )
            locked_row = locked_result.mappings().one_or_none()
            if locked_row is None:
                return KnowledgeSyncResult.failure(
                    KnowledgeSyncErrorCode.SOURCE_NOT_FOUND,
                    retryable=False,
                )
            locked = _snapshot_from_row(locked_row)
            if locked.status == "disabled":
                return KnowledgeSyncResult.failure(
                    KnowledgeSyncErrorCode.SOURCE_DISABLED,
                    retryable=False,
                )
            if command.sync_version < locked.sync_version:
                return KnowledgeSyncResult.no_op()
            if command.sync_version > locked.sync_version:
                return KnowledgeSyncResult.failure(
                    KnowledgeSyncErrorCode.VERSION_AHEAD,
                    retryable=False,
                )

            existing_result = await session.execute(
                _DOCUMENT_BY_VERSION,
                {
                    "tenant_id": command.tenant_id,
                    "source_id": command.source_id,
                    "document_version": command.sync_version,
                },
            )
            existing = existing_result.mappings().one_or_none()
            if existing is not None:
                if existing.get("content_hash") != content_hash:
                    return KnowledgeSyncResult.failure(
                        KnowledgeSyncErrorCode.REPLAY_CONTENT_MISMATCH,
                        retryable=False,
                    )
                document_id = _required_uuid(existing.get("id"))
            else:
                inserted = await session.execute(
                    _DOCUMENT_INSERT,
                    {
                        "tenant_id": command.tenant_id,
                        "source_id": command.source_id,
                        "canonical_uri": fetched.canonical_uri,
                        "title": source.name,
                        "content_hash": content_hash,
                        "document_version": command.sync_version,
                    },
                )
                document_id = _required_uuid(inserted.scalar_one())

            aggregate_id = str(document_id)
            event_exists = await session.execute(
                _PARSE_EVENT_EXISTS,
                {
                    "tenant_id": command.tenant_id,
                    "event_type": PARSE_EVENT_TYPE,
                    "aggregate_id": aggregate_id,
                },
            )
            if event_exists.scalar_one_or_none() is None:
                payload = {
                    "tenantId": str(command.tenant_id),
                    "sourceId": str(command.source_id),
                    "documentId": aggregate_id,
                    "documentVersion": command.sync_version,
                    "sourceType": source.source_type,
                    "rawObjectKey": fetched.raw_object_key,
                    "canonicalUri": fetched.canonical_uri,
                    "contentHash": content_hash,
                }
                await session.execute(
                    _PARSE_EVENT_INSERT,
                    {
                        "tenant_id": command.tenant_id,
                        "event_type": PARSE_EVENT_TYPE,
                        "schema_version": PARSE_SCHEMA_VERSION,
                        "aggregate_id": aggregate_id,
                        "payload": json.dumps(payload, separators=(",", ":"), sort_keys=True),
                        "correlation_id": command.correlation_id,
                        "causation_id": str(command.event_id),
                    },
                )

            await session.execute(
                _SOURCE_SUCCESS_UPDATE,
                {
                    "source_id": command.source_id,
                    "tenant_id": command.tenant_id,
                    "sync_version": command.sync_version,
                },
            )
    return KnowledgeSyncResult.success()


def _snapshot_from_row(row: object) -> _SourceSnapshot:
    get = getattr(row, "get", None)
    if not callable(get):
        raise TypeError("Knowledge source row is not mapping-like.")
    source_type = get("source_type")
    name = get("name")
    source_uri = get("source_uri")
    object_key = get("object_key")
    status = get("status")
    sync_version = get("sync_version")
    if not isinstance(source_type, str) or not isinstance(name, str) or not isinstance(status, str):
        raise TypeError("Knowledge source row contains invalid text fields.")
    if source_uri is not None and not isinstance(source_uri, str):
        raise TypeError("Knowledge source URI is invalid.")
    if object_key is not None and not isinstance(object_key, str):
        raise TypeError("Knowledge source object key is invalid.")
    if isinstance(sync_version, bool) or not isinstance(sync_version, int):
        raise TypeError("Knowledge source sync version is invalid.")
    return _SourceSnapshot(source_type, name, source_uri, object_key, status, sync_version)


def _required_uuid(value: object) -> UUID:
    if not isinstance(value, UUID):
        raise TypeError("Expected UUID database value.")
    return value


def _sync_raw_key(command: KnowledgeSyncCommand) -> str:
    return (
        f"tenants/{command.tenant_id}/knowledge/{command.source_id}/"
        f"sync/{command.sync_version}/raw"
    )


def _is_tenant_source_key(key: str, command: KnowledgeSyncCommand) -> bool:
    prefix = f"tenants/{command.tenant_id}/knowledge/{command.source_id}/"
    return key.startswith(prefix) and "\0" not in key and "\r" not in key and "\n" not in key


def _file_content_type(source_type: str) -> str:
    return {
        "pdf": "application/pdf",
        "markdown": "text/markdown",
        "text": "text/plain",
    }[source_type]
