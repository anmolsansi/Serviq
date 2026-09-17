from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

import pytest

import app.modules.knowledge.cleanup as cleanup
import app.modules.knowledge.quota as quota


def test_quota_logging_uses_fixed_message_and_closed_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_info(message: str, *, extra: dict[str, Any]) -> None:
        captured["message"] = message
        captured["extra"] = extra

    monkeypatch.setattr(quota.logger, "info", fake_info)

    quota._safe_log(
        "attacker\nforged-event",
        tenant_id=uuid4(),
        outcome="attacker\rforged-outcome",
        reserved_bytes=7,
    )

    assert captured["message"] == "knowledge_quota_event"
    assert captured["extra"]["quota_event"] == "knowledge_quota_unknown"
    assert captured["extra"]["quota_outcome"] == "unknown"
    assert captured["extra"]["reserved_bytes"] == 7


def test_cleanup_logging_uses_fixed_message_and_closed_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_log(level: int, message: str, *, extra: dict[str, Any]) -> None:
        captured["level"] = level
        captured["message"] = message
        captured["extra"] = extra

    monkeypatch.setattr(cleanup.logger, "log", fake_log)

    cleanup._safe_log(
        999,
        "attacker\nforged-event",
        cleanup_id=uuid4(),
        tenant_id=uuid4(),
        status="attacker\rforged-status",
        attempt_count=1,
    )

    assert captured["level"] == logging.WARNING
    assert captured["message"] == "knowledge_upload_cleanup_event"
    assert captured["extra"]["cleanup_event"] == "knowledge_upload_cleanup_unknown"
    assert captured["extra"]["cleanup_status"] == "unknown"
