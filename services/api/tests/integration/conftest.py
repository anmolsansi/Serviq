from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import pytest

from app.core.rate_limits import RateLimitDecision
from app.main import app
from app.modules.knowledge.router import get_knowledge_upload_rate_limiter_dependency


class AlwaysAllowKnowledgeUploadRateLimiter:
    async def check_and_consume(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
    ) -> RateLimitDecision:
        del tenant_id, user_id
        return RateLimitDecision(allowed=True)


@pytest.fixture(autouse=True)
def isolate_knowledge_upload_rate_limit() -> Iterator[None]:
    """Keep unrelated DB integration tests deterministic.

    Tests that exercise the limiter contract explicitly replace this same dependency
    with a rejecting/unavailable fake or use a real Valkey integration path.
    """

    dependency = get_knowledge_upload_rate_limiter_dependency
    previous = app.dependency_overrides.get(dependency)
    app.dependency_overrides[dependency] = lambda: AlwaysAllowKnowledgeUploadRateLimiter()
    try:
        yield
    finally:
        if previous is None:
            app.dependency_overrides.pop(dependency, None)
        else:
            app.dependency_overrides[dependency] = previous
