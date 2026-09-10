import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.connectivity import _INTERNAL_TOKEN_ENV
from app.main import app

client = TestClient(app)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    os.environ[_INTERNAL_TOKEN_ENV] = "test-token"
    return {"Authorization": "Bearer test-token"}


def test_embedding_success(auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/internal/v1/embeddings",
        headers=auth_headers,
        json={
            "tenantId": str(uuid4()),
            "modelAlias": "serviq-embedding-v1",
            "purpose": "embedding",
            "inputs": ["Hello world", "Test chunk"],
            "correlationId": "test-123",
        },
    )
    assert response.status_code == 200, response.json()
    data = response.json()
    assert len(data["embeddings"]) == 2
    assert len(data["embeddings"][0]) == 1536
    assert data["provider"] == "openai"
    assert data["upstreamModel"] == "serviq-fake-v1"
    assert data["usage"]["inputTokens"] == 20
    assert data["usage"]["outputTokens"] == 0


def test_embedding_unauthorized() -> None:
    os.environ[_INTERNAL_TOKEN_ENV] = "test-token"
    response = client.post(
        "/internal/v1/embeddings",
        headers={"Authorization": "Bearer bad-token"},
        json={
            "tenantId": str(uuid4()),
            "modelAlias": "serviq-embedding-v1",
            "purpose": "embedding",
            "inputs": ["Hello world"],
            "correlationId": "test-123",
        },
    )
    assert response.status_code == 401


def test_embedding_unsupported_model(auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/internal/v1/embeddings",
        headers=auth_headers,
        json={
            "tenantId": str(uuid4()),
            "modelAlias": "some-unknown-model",
            "purpose": "embedding",
            "inputs": ["Hello world"],
            "correlationId": "test-123",
        },
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "PROVIDER_UNAVAILABLE"


def test_embedding_batch_too_large(auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/internal/v1/embeddings",
        headers=auth_headers,
        json={
            "tenantId": str(uuid4()),
            "modelAlias": "serviq-embedding-v1",
            "purpose": "embedding",
            "inputs": ["Hello"] * 101,  # 1 over the max_length=100 limit
            "correlationId": "test-123",
        },
    )
    assert response.status_code == 422
