"""Bounded multipart parsing for knowledge-source uploads."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

from starlette.datastructures import FormData, Headers
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.requests import Request

from app.modules.knowledge.quota import MAX_KNOWLEDGE_FILE_BYTES
from app.modules.knowledge.uploads import (
    KnowledgeUploadTooLargeError,
    KnowledgeUploadValidationError,
)

_MIB = 1024 * 1024
MAX_KNOWLEDGE_MULTIPART_REQUEST_BYTES = MAX_KNOWLEDGE_FILE_BYTES + _MIB
MAX_KNOWLEDGE_MULTIPART_FIELD_BYTES = 4 * 1024


class _KnowledgeMultipartTooLarge(MultiPartException):
    """Internal parser signal for the approved absolute upload boundary."""


class _KnowledgeMultipartParser(MultiPartParser):
    """Starlette multipart parser with an explicit streamed file-byte ceiling."""

    def __init__(
        self,
        headers: Headers,
        stream: AsyncGenerator[bytes, None],
        *,
        max_files: int | float,
        max_fields: int | float,
        max_part_size: int,
        max_file_bytes: int,
    ) -> None:
        super().__init__(
            headers,
            stream,
            max_files=max_files,
            max_fields=max_fields,
            max_part_size=max_part_size,
        )
        self._max_file_bytes = max_file_bytes
        self._current_file_bytes = 0

    def on_part_begin(self) -> None:
        self._current_file_bytes = 0
        super().on_part_begin()

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._current_part.file is not None:
            self._current_file_bytes += end - start
            if self._current_file_bytes > self._max_file_bytes:
                raise _KnowledgeMultipartTooLarge("Knowledge upload file exceeded the V1 limit.")
        super().on_part_data(data, start, end)


async def _bounded_request_stream(request: Request) -> AsyncGenerator[bytes, None]:
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > MAX_KNOWLEDGE_MULTIPART_REQUEST_BYTES:
            raise _KnowledgeMultipartTooLarge("Knowledge upload request exceeded the V1 limit.")
        yield chunk


async def parse_knowledge_upload_form(request: Request) -> FormData:
    """Parse one bounded upload form without trusting Content-Length."""

    parser = _KnowledgeMultipartParser(
        request.headers,
        _bounded_request_stream(request),
        max_files=1,
        max_fields=3,
        max_part_size=MAX_KNOWLEDGE_MULTIPART_FIELD_BYTES,
        max_file_bytes=MAX_KNOWLEDGE_FILE_BYTES,
    )
    try:
        return await parser.parse()
    except _KnowledgeMultipartTooLarge:
        raise KnowledgeUploadTooLargeError("Uploaded knowledge file exceeds the V1 limit.") from None
    except MultiPartException:
        raise KnowledgeUploadValidationError("Multipart fields are invalid.") from None


@asynccontextmanager
async def open_knowledge_upload_form(request: Request) -> AsyncIterator[FormData]:
    """Parse and always close temporary multipart resources."""

    form = await parse_knowledge_upload_form(request)
    try:
        yield form
    finally:
        await form.close()
