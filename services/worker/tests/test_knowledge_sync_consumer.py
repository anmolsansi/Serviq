from __future__ import annotations

import json
from uuid import uuid4

import pytest

from app.consumers.knowledge_sync import _decode_command, retry_delay_seconds


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

    decoded = json.loads(value)
    decoded["payload"]["tenantId"] = str(uuid4())
    assert _decode_command(key, json.dumps(decoded).encode()) is None

    decoded = json.loads(value)
    decoded["eventType"] = "serviq.knowledge.other.v1"
    assert _decode_command(key, json.dumps(decoded).encode()) is None


def test_malformed_event_fails_closed() -> None:
    assert _decode_command(b"source", b"not-json") is None
