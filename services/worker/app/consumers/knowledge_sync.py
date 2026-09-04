"""Kafka consumer for the frozen V1 knowledge-sync event contract."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from uuid import UUID

import confluent_kafka
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.broker import BrokerUnavailableError, KafkaEventPublisher
from app.core.config import PlatformSettings
from app.core.object_storage import S3RawObjectStorage
from app.jobs.knowledge_sync import (
    KnowledgeSyncCommand,
    KnowledgeSyncResult,
    mark_matching_source_failed,
    run_knowledge_sync,
)

SYNC_TOPIC = "serviq.knowledge.sync.v1"
RETRY_TOPIC = "serviq.knowledge.sync.v1.retry"
DLQ_TOPIC = "serviq.knowledge.sync.v1.dlq"
CONSUMER_GROUP = "serviq-worker-knowledge-sync-v1"
_ATTEMPT_HEADER = "serviq-attempt"
_NOT_BEFORE_HEADER = "serviq-not-before-ms"
_ERROR_HEADER = "serviq-error-code"
_RETRY_DELAYS_SECONDS = (30, 300, 1800)
_POLL_TIMEOUT_SECONDS = 0.1
_INTERNAL_REDELIVERY_DELAY_MS = 1000
_INVALID_EVENT_CODE = "KNOWLEDGE_SYNC_EVENT_INVALID"
_DATABASE_ERROR_CODE = "KNOWLEDGE_SYNC_DATABASE_UNAVAILABLE"


class _SyncPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID = Field(alias="tenantId")
    source_id: UUID = Field(alias="sourceId")
    sync_version: int = Field(alias="syncVersion", ge=1)


class _Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID = Field(alias="id")
    event_type: str = Field(alias="eventType")
    schema_version: int = Field(alias="schemaVersion")
    tenant_id: UUID = Field(alias="tenantId")
    aggregate_type: str = Field(alias="aggregateType")
    aggregate_id: str = Field(alias="aggregateId")
    payload: _SyncPayload
    correlation_id: str = Field(alias="correlationId", min_length=1, max_length=200)
    causation_id: str | None = Field(alias="causationId")


class KnowledgeSyncConsumer:
    """Single durable consumer with manual offset commit and partition-aware delay."""

    def __init__(
        self,
        settings: PlatformSettings,
        session_factory: async_sessionmaker[AsyncSession],
        storage: S3RawObjectStorage,
        publisher: KafkaEventPublisher,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage
        self._publisher = publisher
        self._consumer: Any = confluent_kafka.Consumer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "group.id": CONSUMER_GROUP,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
                "enable.auto.offset.store": False,
                "client.id": "serviq-worker-knowledge-sync",
            }
        )
        self._consumer.subscribe([SYNC_TOPIC, RETRY_TOPIC])
        self._paused_until: dict[tuple[str, int], int] = {}

    async def run_forever(self) -> None:
        """Poll without crossing threads so consumer shutdown cannot race librdkafka."""

        while True:
            self._resume_due_partitions()
            message: Any = self._consumer.poll(_POLL_TIMEOUT_SECONDS)
            # Poll is intentionally short and synchronous. Yield immediately so the
            # outbox publisher coroutine is not starved by an idle consumer.
            await asyncio.sleep(0)
            if message is None or message.error() is not None:
                continue
            await self._handle_message(message)

    async def _handle_message(self, message: Any) -> None:
        headers = _headers_dict(message.headers())
        attempt = 0
        if message.topic() == RETRY_TOPIC:
            retry_metadata = _parse_retry_metadata(headers)
            if retry_metadata is None:
                raw_key, raw_value = _safe_message_bytes(message)
                await self._publish_dlq(
                    message,
                    raw_key,
                    raw_value,
                    _INVALID_EVENT_CODE,
                )
                return
            attempt, not_before_ms = retry_metadata
            now_ms = int(time.time() * 1000)
            if not_before_ms > now_ms:
                self._rewind_and_pause(message, resume_at_ms=not_before_ms)
                return

        raw_key = message.key()
        raw_value = message.value()
        if not isinstance(raw_key, bytes) or not isinstance(raw_value, bytes):
            safe_key, safe_value = _safe_message_bytes(message)
            await self._publish_dlq(message, safe_key, safe_value, _INVALID_EVENT_CODE)
            return

        command = _decode_command(raw_key, raw_value)
        if command is None:
            await self._publish_dlq(message, raw_key, raw_value, _INVALID_EVENT_CODE)
            return

        try:
            result = await run_knowledge_sync(
                self._session_factory,
                self._storage,
                command,
            )
        except SQLAlchemyError:
            result = KnowledgeSyncResult.failure(_DATABASE_ERROR_CODE, retryable=True)

        if result.completed:
            self._commit(message)
            return

        error_code = result.error_code or _INVALID_EVENT_CODE
        if result.retryable and attempt < len(_RETRY_DELAYS_SECONDS):
            await self._publish_retry(message, raw_key, raw_value, attempt + 1)
            return

        try:
            await mark_matching_source_failed(self._session_factory, command, error_code)
        except SQLAlchemyError:
            if attempt < len(_RETRY_DELAYS_SECONDS):
                await self._publish_retry(message, raw_key, raw_value, attempt + 1)
            else:
                # Failure state is part of the terminal contract. Do not advance this
                # partition until the database can record it safely.
                self._rewind_and_pause(message)
            return
        await self._publish_dlq(message, raw_key, raw_value, error_code)

    async def _publish_retry(
        self,
        message: Any,
        key: bytes,
        value: bytes,
        next_attempt: int,
    ) -> None:
        delay_seconds = retry_delay_seconds(next_attempt)
        not_before_ms = int(time.time() * 1000) + delay_seconds * 1000
        headers = {
            _ATTEMPT_HEADER: str(next_attempt).encode("ascii"),
            _NOT_BEFORE_HEADER: str(not_before_ms).encode("ascii"),
        }
        try:
            await self._publisher.publish(
                topic=RETRY_TOPIC,
                key=key,
                value=value,
                headers=headers,
            )
        except BrokerUnavailableError:
            self._rewind_and_pause(message)
            return
        self._commit(message)

    async def _publish_dlq(
        self,
        message: Any,
        key: bytes,
        value: bytes,
        error_code: str,
    ) -> None:
        safe_code = error_code if _is_safe_error_code(error_code) else _INVALID_EVENT_CODE
        headers = {_ERROR_HEADER: safe_code.encode("ascii")}
        try:
            await self._publisher.publish(
                topic=DLQ_TOPIC,
                key=key,
                value=value,
                headers=headers,
            )
        except BrokerUnavailableError:
            self._rewind_and_pause(message)
            return
        self._commit(message)

    def _commit(self, message: Any) -> None:
        self._consumer.commit(message=message, asynchronous=False)

    def _rewind_and_pause(self, message: Any, *, resume_at_ms: int | None = None) -> None:
        topic = message.topic()
        partition_number = message.partition()
        offset = message.offset()
        partition_at_offset = confluent_kafka.TopicPartition(
            topic,
            partition_number,
            offset,
        )
        self._consumer.seek(partition_at_offset)
        self._consumer.pause([confluent_kafka.TopicPartition(topic, partition_number)])
        if resume_at_ms is None:
            resume_at_ms = int(time.time() * 1000) + _INTERNAL_REDELIVERY_DELAY_MS
        self._paused_until[(topic, partition_number)] = resume_at_ms

    def _resume_due_partitions(self) -> None:
        now_ms = int(time.time() * 1000)
        due = [key for key, resume_ms in self._paused_until.items() if resume_ms <= now_ms]
        if not due:
            return
        partitions = [
            confluent_kafka.TopicPartition(topic, partition) for topic, partition in due
        ]
        self._consumer.resume(partitions)
        for key in due:
            del self._paused_until[key]

    def close(self) -> None:
        self._consumer.close()


def retry_delay_seconds(attempt: int) -> int:
    """Return the exact architecture-owned delay for retry attempt 1..3."""

    if isinstance(attempt, bool) or not 1 <= attempt <= len(_RETRY_DELAYS_SECONDS):
        raise ValueError("retry attempt must be between 1 and 3")
    return _RETRY_DELAYS_SECONDS[attempt - 1]


def _decode_command(key: bytes, value: bytes) -> KnowledgeSyncCommand | None:
    try:
        decoded = json.loads(value.decode("utf-8"))
        envelope = _Envelope.model_validate(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError):
        return None
    payload = envelope.payload
    if envelope.event_type != SYNC_TOPIC or envelope.schema_version != 1:
        return None
    if envelope.aggregate_type != "knowledge_source":
        return None
    if envelope.aggregate_id != str(payload.source_id):
        return None
    if key != envelope.aggregate_id.encode("utf-8"):
        return None
    if envelope.tenant_id != payload.tenant_id:
        return None
    return KnowledgeSyncCommand(
        event_id=envelope.event_id,
        tenant_id=payload.tenant_id,
        source_id=payload.source_id,
        sync_version=payload.sync_version,
        correlation_id=envelope.correlation_id,
    )


def _headers_dict(headers: Any) -> dict[str, bytes]:
    if not isinstance(headers, list):
        return {}
    parsed: dict[str, bytes] = {}
    for item in headers:
        if not isinstance(item, tuple) or len(item) != 2:
            continue
        key, value = item
        if isinstance(key, str) and isinstance(value, bytes):
            parsed[key] = value
    return parsed


def _parse_retry_metadata(headers: dict[str, bytes]) -> tuple[int, int] | None:
    attempt = _parse_positive_ascii_int(headers.get(_ATTEMPT_HEADER))
    not_before_ms = _parse_positive_ascii_int(headers.get(_NOT_BEFORE_HEADER))
    if attempt is None or not_before_ms is None:
        return None
    if attempt > len(_RETRY_DELAYS_SECONDS):
        return None
    return attempt, not_before_ms


def _parse_positive_ascii_int(value: bytes | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value.decode("ascii"), 10)
    except (UnicodeDecodeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _safe_message_bytes(message: Any) -> tuple[bytes, bytes]:
    raw_key = message.key()
    raw_value = message.value()
    key = raw_key if isinstance(raw_key, bytes) else b""
    value = raw_value if isinstance(raw_value, bytes) else b""
    return key, value


def _is_safe_error_code(value: str) -> bool:
    if not value or len(value) > 100:
        return False
    return all(char.isupper() or char.isdigit() or char == "_" for char in value)
