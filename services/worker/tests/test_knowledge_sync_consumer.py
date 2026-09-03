from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any, cast
from uuid import uuid4

import pytest

from app.consumers.knowledge_sync import (
    DLQ_TOPIC,
    RETRY_TOPIC,
    KnowledgeSyncConsumer,
    _decode_command,
    retry_delay_seconds,
)
from app.core.broker import BrokerUnavailableError, KafkaEventPublisher


class _FakeConsumer:
    def __init__(self) -> None:
        self.commits: list[object] = []

    def commit(self, *, message: object, asynchronous: bool) -> None:
        assert asynchronous is False
        self.commits.append(message)


class _RecordingPublisher:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.records: list[tuple[str, bytes, bytes, Mapping[str, bytes] | None]] = []

    async def publish(
        self,
        *,
        topic: str,
        key: bytes,
        value: bytes,
        headers: Mapping[str, bytes] | None = None,
    ) -> None:
        if self.fail:
            raise BrokerUnavailableError
        self.records.append((topic, key, value, headers))


class _Message:
    pass


def _event_bytes() -> tuple[bytes, bytes]:
    tenant_id = uuid4()
    source_id = uuid4()
    event_id = uuid4()
    aggregate_id = str(source_id)
    envelope = {
        "id": str(event_id),
        "eventType": "serviq.knowledge.sync.v1",
        "schemaVersion": 1,
        "tenantId": str(tenant_id),
        "aggregateType": "knowledge_source",
        "aggregateId": aggregate_id,
        "payload": {
            "tenantId": str(tenant_id),
            "sourceId": str(source_id),
            "syncVersion": 4,
        },
        "correlationId": "request-123",
        "causationId": None,
    }
    return aggregate_id.encode(), json.dumps(envelope).encode()


def _consumer_with_fakes(
    kafka_consumer: _FakeConsumer,
    publisher: _RecordingPublisher,
) -> KnowledgeSyncConsumer:
    consumer = cast(KnowledgeSyncConsumer, object.__new__(KnowledgeSyncConsumer))
    consumer._consumer = kafka_consumer
    consumer._publisher = cast(KafkaEventPublisher, publisher)
    return consumer


def test_exact_retry_schedule() -> None:
    assert retry_delay_seconds(1) == 30
    assert retry_delay_seconds(2) == 300
    assert retry_delay_seconds(3) == 1800
    with pytest.raises(ValueError):
        retry_delay_seconds(0)
    with pytest.raises(ValueError):
        retry_delay_seconds(4)


def test_valid_sync_envelope_decodes_to_command() -> None:
    key, value = _event_bytes()

    command = _decode_command(key, value)

    assert command is not None
    assert command.sync_version == 4
    assert command.correlation_id == "request-123"
    assert key == str(command.source_id).encode()


def test_key_tenant_and_contract_mismatches_fail_closed() -> None:
    key, value = _event_bytes()
    assert _decode_command(b"wrong-key", value) is None

    decoded: dict[str, Any] = json.loads(value)
    decoded["payload"]["tenantId"] = str(uuid4())
    assert _decode_command(key, json.dumps(decoded).encode()) is None

    decoded = json.loads(value)
    decoded["eventType"] = "serviq.knowledge.other.v1"
    assert _decode_command(key, json.dumps(decoded).encode()) is None


def test_malformed_event_fails_closed() -> None:
    assert _decode_command(b"source", b"not-json") is None


def test_retry_publish_failure_does_not_commit_original_offset() -> None:
    async def scenario() -> None:
        kafka_consumer = _FakeConsumer()
        publisher = _RecordingPublisher(fail=True)
        consumer = _consumer_with_fakes(kafka_consumer, publisher)
        message = _Message()

        await consumer._publish_retry(message, b"source", b"event", 1)

        assert kafka_consumer.commits == []
        assert publisher.records == []

    asyncio.run(scenario())


def test_successful_retry_publish_commits_with_exact_headers() -> None:
    async def scenario() -> None:
        kafka_consumer = _FakeConsumer()
        publisher = _RecordingPublisher()
        consumer = _consumer_with_fakes(kafka_consumer, publisher)
        message = _Message()

        await consumer._publish_retry(message, b"source", b"event", 2)

        assert kafka_consumer.commits == [message]
        assert len(publisher.records) == 1
        topic, key, value, headers = publisher.records[0]
        assert topic == RETRY_TOPIC
        assert key == b"source"
        assert value == b"event"
        assert headers is not None
        assert headers["serviq-attempt"] == b"2"
        assert int(headers["serviq-not-before-ms"].decode("ascii")) > 0

    asyncio.run(scenario())


def test_dlq_publish_failure_does_not_commit_original_offset() -> None:
    async def scenario() -> None:
        kafka_consumer = _FakeConsumer()
        publisher = _RecordingPublisher(fail=True)
        consumer = _consumer_with_fakes(kafka_consumer, publisher)
        message = _Message()

        await consumer._publish_dlq(
            message,
            b"source",
            b"event",
            "KNOWLEDGE_SOURCE_DISABLED",
        )

        assert kafka_consumer.commits == []

    asyncio.run(scenario())


def test_successful_dlq_publish_commits_safe_error_header() -> None:
    async def scenario() -> None:
        kafka_consumer = _FakeConsumer()
        publisher = _RecordingPublisher()
        consumer = _consumer_with_fakes(kafka_consumer, publisher)
        message = _Message()

        await consumer._publish_dlq(
            message,
            b"source",
            b"event",
            "KNOWLEDGE_SOURCE_DISABLED",
        )

        assert kafka_consumer.commits == [message]
        assert publisher.records == [
            (
                DLQ_TOPIC,
                b"source",
                b"event",
                {"serviq-error-code": b"KNOWLEDGE_SOURCE_DISABLED"},
            )
        ]

    asyncio.run(scenario())
