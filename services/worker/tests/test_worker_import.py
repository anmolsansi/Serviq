from __future__ import annotations

from collections.abc import Coroutine
from typing import Any

from app.main import main


def test_worker_entry_point_wires_async_runtime_without_external_connections() -> None:
    called = False

    def fake_runner(coroutine: Coroutine[Any, Any, None]) -> None:
        nonlocal called
        called = True
        coroutine.close()

    assert main(runner=fake_runner) == 0
    assert called is True
