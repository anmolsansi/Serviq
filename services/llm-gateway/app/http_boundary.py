"""Pre-parse safety boundary for Serviq's private LLM gateway HTTP routes."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.connectivity import _require_internal_token
from app.schemas import MAX_EMBEDDING_BATCH_SIZE, MAX_EMBEDDING_INPUT_CHARS

# JSON may encode a single character as a six-byte ``\uXXXX`` escape. The fixed
# allowance covers the remaining C-4 fields and JSON structure without making the
# transport body unbounded.
MAX_INTERNAL_REQUEST_BODY_BYTES = (
    MAX_EMBEDDING_BATCH_SIZE * MAX_EMBEDDING_INPUT_CHARS * 6
) + (128 * 1024)
_INTERNAL_PREFIX = "/internal/v1/"
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})


class _RequestBodyTooLarge(Exception):
    """Raised before application parsing when the transport body exceeds its cap."""


def _detail_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": {"code": code, "message": message}},
    )


class InternalGatewayBoundaryMiddleware:
    """Authenticate and bound private request bodies before FastAPI parses them."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or not scope["path"].startswith(_INTERNAL_PREFIX)
            or scope["method"] not in _BODY_METHODS
        ):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        try:
            _require_internal_token(headers.get("authorization"))
        except HTTPException as error:
            response = JSONResponse(
                status_code=error.status_code,
                content={"detail": error.detail},
                headers=error.headers,
            )
            await response(scope, receive, send)
            return

        declared_length = headers.get("content-length")
        if declared_length is not None:
            try:
                body_length = int(declared_length)
            except ValueError:
                response = _detail_response(
                    status.HTTP_400_BAD_REQUEST,
                    "INVALID_CONTENT_LENGTH",
                    "Invalid Content-Length header.",
                )
                await response(scope, receive, send)
                return
            if body_length < 0:
                response = _detail_response(
                    status.HTTP_400_BAD_REQUEST,
                    "INVALID_CONTENT_LENGTH",
                    "Invalid Content-Length header.",
                )
                await response(scope, receive, send)
                return
            if body_length > MAX_INTERNAL_REQUEST_BODY_BYTES:
                response = _detail_response(
                    status.HTTP_413_CONTENT_TOO_LARGE,
                    "REQUEST_BODY_TOO_LARGE",
                    "Request body exceeds the allowed size.",
                )
                await response(scope, receive, send)
                return

        received_bytes = 0

        async def receive_limited() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > MAX_INTERNAL_REQUEST_BODY_BYTES:
                    raise _RequestBodyTooLarge
            return message

        try:
            await self.app(scope, receive_limited, send)
        except _RequestBodyTooLarge:
            response = _detail_response(
                status.HTTP_413_CONTENT_TOO_LARGE,
                "REQUEST_BODY_TOO_LARGE",
                "Request body exceeds the allowed size.",
            )
            await response(scope, receive, send)


def register_gateway_error_handlers(app: FastAPI) -> None:
    """Install input-safe error handlers for validation performed by FastAPI/Pydantic."""

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        # RequestValidationError.errors() includes the rejected ``input`` value.
        # Never serialize it on this private data path.
        del request, error
        return _detail_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_REQUEST",
            "Request validation failed.",
        )
