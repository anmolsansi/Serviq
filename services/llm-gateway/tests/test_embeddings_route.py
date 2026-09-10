from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

import app.routing.embeddings as embeddings_route
from app.adapters import AdapterContext, FakeLLMAdapter, FakeScenario
from app.connectivity import _INTERNAL_TOKEN_ENV
from app.main import app
from app.schemas import (
    EMBEDDING_DIMENSION,
    MAX_EMBEDDING_BATCH_SIZE,
    MAX_EMBEDDING_INPUT_CHARS,
    GatewayEmbeddingRequest,
    GatewayEmbeddingResponse,
    GatewayProvider,
    GatewayUsage,
)

client = TestClient(app)
_TENANT_ID = UUID("00000000-0000-0000-0000-000000000011")
_INPUT_SENTINEL = "raw-private-knowledge-must-not-leak"


@pytest.fixture
def auth_headers(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.setenv(_INTERNAL_TOKEN_ENV, "test-token")
    return {"Authorization": "Bearer test-token"}


def _payload(
    *,
    inputs: list[str] | None = None,
    model_alias: str = "serviq-embedding-v1",
    purpose: str = "embedding",
    correlation_id: str = "v1.3.11-test",
) -> dict[str, object]:
    return {
        "tenantId": str(_TENANT_ID),
        "modelAlias": model_alias,
        "purpose": purpose,
        "inputs": ["Hello world", "Test chunk"] if inputs is None else inputs,
        "correlationId": correlation_id,
    }


def _context() -> AdapterContext:
    return AdapterContext(
        provider=GatewayProvider.OPENAI,
        upstream_model="serviq-fake-v1",
        api_key=None,
    )


def test_embedding_success_preserves_order_and_dimension(
    auth_headers: dict[str, str],
) -> None:
    response = client.post(
        "/internal/v1/embeddings",
        headers=auth_headers,
        json=_payload(),
    )

    assert response.status_code == 200, response.json()
    data = response.json()
    assert len(data["embeddings"]) == 2
    assert all(len(vector) == EMBEDDING_DIMENSION for vector in data["embeddings"])
    assert data["embeddings"][0] != data["embeddings"][1]
    assert data["provider"] == "openai"
    assert data["upstreamModel"] == "serviq-fake-v1"
    assert data["usage"] == {"inputTokens": 20, "outputTokens": 0}
    assert data["requestId"].startswith("fake_")


def test_embedding_repeat_is_exactly_deterministic(
    auth_headers: dict[str, str],
) -> None:
    payload = _payload(inputs=["same input", "second input"])

    first = client.post("/internal/v1/embeddings", headers=auth_headers, json=payload)
    second = client.post("/internal/v1/embeddings", headers=auth_headers, json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()


def test_embedding_batch_boundaries(auth_headers: dict[str, str]) -> None:
    accepted = client.post(
        "/internal/v1/embeddings",
        headers=auth_headers,
        json=_payload(inputs=["bounded"] * MAX_EMBEDDING_BATCH_SIZE),
    )
    rejected = client.post(
        "/internal/v1/embeddings",
        headers=auth_headers,
        json=_payload(inputs=["bounded"] * (MAX_EMBEDDING_BATCH_SIZE + 1)),
    )

    assert accepted.status_code == 200
    assert len(accepted.json()["embeddings"]) == MAX_EMBEDDING_BATCH_SIZE
    assert rejected.status_code == 422


def test_embedding_input_size_boundaries(auth_headers: dict[str, str]) -> None:
    accepted = client.post(
        "/internal/v1/embeddings",
        headers=auth_headers,
        json=_payload(inputs=["a" * MAX_EMBEDDING_INPUT_CHARS]),
    )
    rejected = client.post(
        "/internal/v1/embeddings",
        headers=auth_headers,
        json=_payload(inputs=["a" * (MAX_EMBEDDING_INPUT_CHARS + 1)]),
    )

    assert accepted.status_code == 200
    assert rejected.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        _payload(inputs=[]),
        _payload(inputs=["   "]),
        _payload(purpose="generation"),
    ],
)
def test_embedding_malformed_contract_is_rejected(
    auth_headers: dict[str, str],
    payload: dict[str, object],
) -> None:
    response = client.post(
        "/internal/v1/embeddings",
        headers=auth_headers,
        json=payload,
    )

    assert response.status_code == 422


def test_embedding_requires_existing_internal_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_INTERNAL_TOKEN_ENV, "test-token")
    unauthorized = client.post(
        "/internal/v1/embeddings",
        headers={"Authorization": "Bearer bad-token"},
        json=_payload(),
    )
    assert unauthorized.status_code == 401

    monkeypatch.delenv(_INTERNAL_TOKEN_ENV)
    unavailable = client.post("/internal/v1/embeddings", json=_payload())
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"]["code"] == "INTERNAL_GATEWAY_AUTH_UNAVAILABLE"


def test_embedding_unsupported_alias_fails_closed(auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/internal/v1/embeddings",
        headers=auth_headers,
        json=_payload(model_alias="fake-embedding"),
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "PROVIDER_UNAVAILABLE",
        "message": "Embedding profile is unavailable.",
    }


def test_embedding_provider_failure_is_normalized_without_input_disclosure(
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_resolver(model_alias: str) -> tuple[FakeLLMAdapter, AdapterContext]:
        assert model_alias == "serviq-embedding-v1"
        return FakeLLMAdapter(FakeScenario.UNAVAILABLE), _context()

    monkeypatch.setattr(embeddings_route, "_resolve_adapter", failing_resolver)
    response = client.post(
        "/internal/v1/embeddings",
        headers=auth_headers,
        json=_payload(inputs=[_INPUT_SENTINEL]),
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "PROVIDER_UNAVAILABLE"
    assert _INPUT_SENTINEL not in response.text


class _MismatchedEmbeddingAdapter:
    async def embed(
        self,
        request: GatewayEmbeddingRequest,
        context: AdapterContext,
    ) -> GatewayEmbeddingResponse:
        del request
        return GatewayEmbeddingResponse(
            embeddings=[[0.0] * EMBEDDING_DIMENSION],
            provider=context.provider,
            upstreamModel=context.upstream_model,
            usage=GatewayUsage(inputTokens=1, outputTokens=0),
            requestId="mismatch-test",
        )


def test_embedding_response_count_mismatch_fails_closed(
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _MismatchedEmbeddingAdapter()

    def mismatched_resolver(
        model_alias: str,
    ) -> tuple[_MismatchedEmbeddingAdapter, AdapterContext]:
        assert model_alias == "serviq-embedding-v1"
        return adapter, _context()

    monkeypatch.setattr(embeddings_route, "_resolve_adapter", mismatched_resolver)
    response = client.post(
        "/internal/v1/embeddings",
        headers=auth_headers,
        json=_payload(inputs=["first", "second"]),
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "PROVIDER_UNAVAILABLE",
        "message": "Embedding provider returned an invalid batch response.",
    }
