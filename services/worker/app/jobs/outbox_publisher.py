"""Generic PostgreSQL transactional-outbox publisher job."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.broker import BrokerUnavailableError, EventPublisher

DEFAULT_BATCH_SIZE = 20
MAX_BATCH_SIZE = 100
_BASE_RETRY_SECONDS = 5
_MAX_RETRY_SECONDS = 300

_CLAIM_DUE_EVENTS = text(
    """
    SELECT id, tenant_id, event_type, schema_version, aggregate_type, aggregate_id,
           payload, correlation_id, causation_id, attempts
    FROM outbox_events
    WHERE status = 'pending'
      AND next_attempt_at <= now()
    ORDER BY next_attempt_at ASC, id ASC
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
    """
)

_MARK_PUBLISHED = text(
    """
    UPDATE outbox_events
    SET status = 'published',
        published_at = now()
    WHERE id = :event_id
      AND status = 'pending'
    """
)

_MARK_RETRY = text(
    """
    UPDATE outbox_events
    SET attempts = :attempts,
        next_attempt_at = now() + (:delay_seconds * interval '1 second')
    WHERE id = :event_id
      AND status = 'pending'
    """
)

_MARK_FAILED = text(
    """
    UPDATE outbox_events
    SET status = 'failed',
        attempts = attempts + 1
    WHERE id = :event_id
      AND status = 'pending'
    """
)


class OutboxSerializationError(RuntimeError):
    """Stable terminal error for a malformed durable outbox row."""

    def __init__(self) -> None:
        super().__init__("Outbox event does not satisfy the frozen wire contract.")


@dataclass(frozen=True, slots=True)
class BrokerRecord:
    topic: str
    key: bytes
    value: bytes


def publisher_backoff_seconds(attempts_after_failure: int) -> int:
    """Return the frozen deterministic publisher retry delay."""

    if isinstance(attempts_after_failure, bool) or attempts_after_failure < 1:
        raise ValueError("attempts_after_failure must be a positive integer")
    if attempts_after_failure >= 7:
        return _MAX_RETRY_SECONDS
    return min(
        _BASE_RETRY_SECONDS * (2 ** (attempts_after_failure - 1)),
        _MAX_RETRY_SECONDS,
    )


def _required_uuid(value: object) -> UUID:
    if not isinstance(value, UUID):
        raise OutboxSerializationError
    return value


def _optional_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    return _required_uuid(value)


def _required_text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise OutboxSerializationError
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _required_text(value)


def _required_positive_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise OutboxSerializationError
    return value


def _required_nonnegative_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise OutboxSerializationError
    return value


def serialize_outbox_row(row: Mapping[str, object]) -> BrokerRecord:
    """Serialize one database row to the exact ADR-022 Kafka envelope."""

    event_id = _required_uuid(row.get("id"))
    tenant_id = _optional_uuid(row.get("tenant_id"))
    event_type = _required_text(row.get("event_type"))
    schema_version = _required_positive_int(row.get("schema_version"))
    aggregate_type = _required_text(row.get("aggregate_type"))
    aggregate_id = _required_text(row.get("aggregate_id"))
    correlation_id = _required_text(row.get("correlation_id"))
    causation_id = _optional_text(row.get("causation_id"))
    payload = row.get("payload")
    if not isinstance(payload, dict):
        raise OutboxSerializationError

    envelope: dict[str, object] = {
        "id": str(event_id),
        "eventType": event_type,
        "schemaVersion": schema_version,
        "tenantId": None if tenant_id is None else str(tenant_id),
        "aggregateType": aggregate_type,
        "aggregateId": aggregate_id,
        "payload": payload,
        "correlationId": correlation_id,
        "causationId": causation_id,
    }
    try:
        value = json.dumps(
            envelope,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise OutboxSerializationError from None

    return BrokerRecord(
        topic=event_type,
        key=aggregate_id.encode("utf-8"),
        value=value,
    )


async def publish_due_batch(
    session: AsyncSession,
    publisher: EventPublisher,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """Claim and attempt one bounded batch of due outbox rows."""

    if isinstance(batch_size, bool) or not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}")

    processed = 0
    async with session.begin():
        result = await session.execute(_CLAIM_DUE_EVENTS, {"batch_size": batch_size})
        rows = result.mappings().all()

        for row in rows:
            event_id = _required_uuid(row.get("id"))
            attempts = _required_nonnegative_int(row.get("attempts"))
            processed += 1

            try:
                record = serialize_outbox_row(row)
            except OutboxSerializationError:
                await session.execute(_MARK_FAILED, {"event_id": event_id})
                continue

            try:
                await publisher.publish(
                    topic=record.topic,
                    key=record.key,
                    value=record.value,
                )
            except BrokerUnavailableError:
                attempts_after_failure = attempts + 1
                await session.execute(
                    _MARK_RETRY,
                    {
                        "event_id": event_id,
                        "attempts": attempts_after_failure,
                        "delay_seconds": publisher_backoff_seconds(attempts_after_failure),
                    },
                )
                continue

            await session.execute(_MARK_PUBLISHED, {"event_id": event_id})

    return processed
