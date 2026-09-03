from __future__ import annotations

import json
from uuid import UUID

import pytest

from app.jobs.outbox_publisher import (
    OutboxSerializationError,
    publisher_backoff_seconds,
    serialize_outbox_row,
)

EVENT_ID = UUID("018f0000-0000-7000-8000-000000000001")
TENANT_ID = UUID("018f0000-0000-7000-8000-000000000002")


def _valid_row() -> dict[str, object]:
    return {
        "id": EVENT_ID,
        "tenant_id": TENANT_ID,
        "event_type": "serviq.knowledge.sync.v1",
        "schema_version": 1,
        "aggregate_type": "knowledge_source",
        "aggregate_id": "018f0000-0000-7000-8000-000000000003",
        "payload": {"syncVersion": 3},
        "correlation_id": "req-123",
        "causation_id": None,
        "attempts": 0,
    }


def test_serializes_exact_topic_key_and_envelope() -> None:
    record = serialize_outbox_row(_valid_row())

    assert record.topic == "serviq.knowledge.sync.v1"
    assert record.key == b"018f0000-0000-7000-8000-000000000003"
    assert json.loads(record.value) == {
        "id": str(EVENT_ID),
        "eventType": "serviq.knowledge.sync.v1",
        "schemaVersion": 1,
        "tenantId": str(TENANT_ID),
        "aggregateType": "knowledge_source",
        "aggregateId": "018f0000-0000-7000-8000-000000000003",
        "payload": {"syncVersion": 3},
        "correlationId": "req-123",
        "causationId": None,
    }


def test_serialization_is_deterministic() -> None:
    first = serialize_outbox_row(_valid_row())
    second = serialize_outbox_row(_valid_row())

    assert first.value == second.value


@pytest.mark.parametrize(
    ("attempts", "expected"),
    [(1, 5), (2, 10), (3, 20), (4, 40), (5, 80), (6, 160), (7, 300), (20, 300)],
)
def test_publisher_backoff_is_bounded(attempts: int, expected: int) -> None:
    assert publisher_backoff_seconds(attempts) == expected


@pytest.mark.parametrize("attempts", [0, -1, True])
def test_invalid_backoff_attempts_are_rejected(attempts: int) -> None:
    with pytest.raises(ValueError):
        publisher_backoff_seconds(attempts)


def test_non_object_payload_is_terminal_serialization_error() -> None:
    row = _valid_row() | {"payload": ["not", "an", "object"]}

    with pytest.raises(OutboxSerializationError):
        serialize_outbox_row(row)


def test_missing_required_contract_field_is_terminal_serialization_error() -> None:
    row = _valid_row()
    del row["aggregate_id"]

    with pytest.raises(OutboxSerializationError):
        serialize_outbox_row(row)
