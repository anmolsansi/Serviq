from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from tempfile import SpooledTemporaryFile
from unittest.mock import patch

import pytest
from starlette.datastructures import Headers, UploadFile
from starlette.requests import Request
from starlette.types import Message

from app.modules.knowledge import multipart as knowledge_multipart
from app.modules.knowledge.multipart import (
    _KnowledgeMultipartParser,
    _KnowledgeMultipartTooLarge,
    open_knowledge_upload_form,
    parse_knowledge_upload_form,
)
from app.modules.knowledge.uploads import (
    KnowledgeUploadTooLargeError,
    KnowledgeUploadValidationError,
)


def _multipart_body(*, boundary: str, file_bytes: bytes = b"safe") -> bytes:
    return (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="sourceType"\r\n\r\n'
        "text\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="name"\r\n\r\n'
        "Upload\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="accessScope"\r\n\r\n'
        "customer\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="upload.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
    ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()


def _request_for_chunks(*, boundary: str, chunks: list[bytes]) -> tuple[Request, list[Message]]:
    messages: list[Message] = [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ]
    delivered: list[Message] = []

    async def receive() -> Message:
        message = messages.pop(0)
        delivered.append(message)
        return message

    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/knowledge-sources",
            "raw_path": b"/api/v1/knowledge-sources",
            "query_string": b"",
            "headers": [
                (
                    b"content-type",
                    f"multipart/form-data; boundary={boundary}".encode(),
                )
            ],
            "client": ("127.0.0.1", 1234),
            "server": ("test", 80),
        },
        receive,
    )
    return request, delivered


def test_parser_stops_oversized_file_and_closes_tempfile() -> None:
    async def scenario() -> None:
        boundary = "serviq-boundary"
        body = _multipart_body(boundary=boundary, file_bytes=b"12345")

        async def stream() -> AsyncGenerator[bytes]:
            yield body

        tempfile = SpooledTemporaryFile[bytes]()
        parser = _KnowledgeMultipartParser(
            Headers({"Content-Type": f"multipart/form-data; boundary={boundary}"}),
            stream(),
            max_files=1,
            max_fields=3,
            max_part_size=4096,
            max_file_bytes=4,
        )
        with (
            patch("starlette.formparsers.SpooledTemporaryFile", return_value=tempfile),
            pytest.raises(_KnowledgeMultipartTooLarge),
        ):
            await parser.parse()
        assert tempfile.closed

    asyncio.run(scenario())


def test_streamed_total_limit_does_not_require_content_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        boundary = "serviq-boundary"
        body = _multipart_body(boundary=boundary, file_bytes=b"safe")
        split = len(body) // 2
        request, delivered = _request_for_chunks(
            boundary=boundary,
            chunks=[body[:split], body[split:]],
        )
        monkeypatch.setattr(
            knowledge_multipart,
            "MAX_KNOWLEDGE_MULTIPART_REQUEST_BYTES",
            len(body) - 1,
        )

        with pytest.raises(KnowledgeUploadTooLargeError):
            await parse_knowledge_upload_form(request)
        assert len(delivered) == 2

    asyncio.run(scenario())


def test_upload_form_context_closes_parsed_file() -> None:
    async def scenario() -> None:
        boundary = "serviq-boundary"
        request, _ = _request_for_chunks(
            boundary=boundary,
            chunks=[_multipart_body(boundary=boundary)],
        )

        async with open_knowledge_upload_form(request) as form:
            upload = form.get("file")
            assert isinstance(upload, UploadFile)
            assert not upload.file.closed
        assert upload.file.closed

    asyncio.run(scenario())


def test_malformed_multipart_maps_to_safe_validation_error() -> None:
    async def scenario() -> None:
        async def receive() -> Message:
            return {"type": "http.request", "body": b"", "more_body": False}

        request = Request(
            {
                "type": "http",
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/api/v1/knowledge-sources",
                "raw_path": b"/api/v1/knowledge-sources",
                "query_string": b"",
                "headers": [(b"content-type", b"multipart/form-data")],
                "client": ("127.0.0.1", 1234),
                "server": ("test", 80),
            },
            receive,
        )
        with pytest.raises(KnowledgeUploadValidationError):
            await parse_knowledge_upload_form(request)

    asyncio.run(scenario())
