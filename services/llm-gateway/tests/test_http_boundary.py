from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

import app.http_boundary as http_boundary
from app.connectivity import _INTERNAL_TOKEN_ENV
from app.main import app
from app.schemas import MAX_EMBEDDING_INPUT_CHARS

client = TestClient(app)
_INPUT_SENTINEL = "raw-private-knowledge-must-not-leak"
_SECRET_SENTINEL = "provider-secret-must-not-leak"


@pytest.fixture
def auth_headers(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.setenv(_INTERNAL_TOKEN_ENV, "test-token")
    return {"Authorization": "Bearer test-token"}


def _payload(inputs: list[str]) -> dict[str, object]:
    return {
        "tenantId": "00000000-0000-0000-0000-000000000011",
        "modelAlias": "serviq-embedding-v1",
        "purpose": "embedding",
        "inputs": inputs,
        "correlationId": "v1.3.11a-http-boundary-test",
    }


def test_validation_error_redacts_rejected_embedding_input(
    auth_headers: dict[str, str],
) -> None:
    rejected_input = _INPUT_SENTINEL + ("x" * MAX_EMBEDDING_INPUT_CHARS)

    response = client.post(
        "/internal/v1/embeddings",
        headers=auth_headers,
        json=_payload([rejected_input]),
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "INVALID_REQUEST",
            "message": "Request validation failed.",
        }
    }
    assert _INPUT_SENTINEL not in response.text


def test_validation_error_redacts_rejected_provider_secret(
    auth_headers: dict[str, str],
) -> None:
    rejected_secret = _SECRET_SENTINEL + ("x" * 4096)

    response = client.post(
        "/internal/v1/provider-connectivity-test",
        headers=auth_headers,
        json={
            "tenantId": "00000000-0000-0000-0000-000000000011",
            "provider": "openai",
            "apiKey": rejected_secret,
            "correlationId": "v1.3.11a-secret-redaction-test",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "INVALID_REQUEST",
            "message": "Request validation failed.",
        }
    }
    assert _SECRET_SENTINEL not in response.text
    assert rejected_secret not in response.text


def test_unauthorized_malformed_body_is_rejected_before_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_INTERNAL_TOKEN_ENV, "test-token")
    malformed = f'{{"inputs":["{_INPUT_SENTINEL}"'.encode()

    response = client.post(
        "/internal/v1/embeddings",
        headers={
            "Authorization": "Bearer wrong-token",
            "Content-Type": "application/json",
        },
        content=malformed,
    )

    assert response.status_code == 401
    assert response.json()["detail"] == {
        "code": "UNAUTHORIZED",
        "message": "Unauthorized.",
    }
    assert _INPUT_SENTINEL not in response.text


def test_unconfigured_auth_fails_before_malformed_body_is_parsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(_INTERNAL_TOKEN_ENV, raising=False)
    malformed = f'{{"inputs":["{_INPUT_SENTINEL}"'.encode()

    response = client.post(
        "/internal/v1/embeddings",
        headers={"Content-Type": "application/json"},
        content=malformed,
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "INTERNAL_GATEWAY_AUTH_UNAVAILABLE",
        "message": "Gateway unavailable.",
    }
    assert _INPUT_SENTINEL not in response.text


def test_declared_oversize_body_is_rejected_before_parsing(
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(http_boundary, "MAX_INTERNAL_REQUEST_BODY_BYTES", 128)
    body = ("x" * 256).encode()

    response = client.post(
        "/internal/v1/embeddings",
        headers={**auth_headers, "Content-Type": "application/json"},
        content=body,
    )

    assert response.status_code == 413
    assert response.json()["detail"] == {
        "code": "REQUEST_BODY_TOO_LARGE",
        "message": "Request body exceeds the allowed size.",
    }


def test_streamed_body_limit_does_not_trust_understated_content_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_INTERNAL_TOKEN_ENV, "test-token")
    monkeypatch.setattr(http_boundary, "MAX_INTERNAL_REQUEST_BODY_BYTES", 128)
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/internal/v1/embeddings",
        "raw_path": b"/internal/v1/embeddings",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"authorization", b"Bearer test-token"),
            (b"content-type", b"application/json"),
            (b"content-length", b"1"),
        ],
        "client": ("test", 50000),
        "server": ("test", 80),
        "extensions": {},
        "state": {},
    }
    incoming: list[Message] = [
        {
            "type": "http.request",
            "body": b"x" * 256,
            "more_body": False,
        }
    ]
    response_statuses: list[int] = []

    async def receive() -> Message:
        return incoming.pop(0)

    async def send(message: Message) -> None:
        if message["type"] == "http.response.start":
            response_statuses.append(int(message["status"]))

    async def downstream(
        child_scope: Scope,
        child_receive: Receive,
        child_send: Send,
    ) -> None:
        del child_scope, child_send
        await child_receive()

    middleware = http_boundary.InternalGatewayBoundaryMiddleware(downstream)
    asyncio.run(middleware(scope, receive, send))

    assert response_statuses == [413]


def test_unauthorized_request_wins_over_body_size_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_INTERNAL_TOKEN_ENV, "test-token")
    monkeypatch.setattr(http_boundary, "MAX_INTERNAL_REQUEST_BODY_BYTES", 32)

    response = client.post(
        "/internal/v1/embeddings",
        headers={
            "Authorization": "Bearer wrong-token",
            "Content-Type": "application/json",
        },
        content=("x" * 256).encode(),
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "UNAUTHORIZED"
