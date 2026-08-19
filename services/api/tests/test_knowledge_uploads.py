from __future__ import annotations

import asyncio
from tempfile import SpooledTemporaryFile

import pytest
from starlette.datastructures import Headers, UploadFile

from app.modules.knowledge.uploads import (
    KnowledgeUploadTooLargeError,
    KnowledgeUploadValidationError,
    validate_upload,
)


def _upload(filename: str, content_type: str, data: bytes) -> UploadFile:
    file = SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b")
    file.write(data)
    file.seek(0)
    return UploadFile(
        file=file,
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def test_valid_pdf_markdown_and_text_uploads() -> None:
    async def scenario() -> None:
        pdf = await validate_upload(
            _upload("guide.pdf", "application/pdf", b"%PDF-1.7\nfixture"),
            source_type="pdf",
        )
        markdown = await validate_upload(
            _upload("guide.markdown", "text/plain", b"# Help\nSafe text"),
            source_type="markdown",
        )
        text = await validate_upload(
            _upload("guide.txt", "text/plain", b"hello"),
            source_type="text",
        )
        assert pdf.content_type == "application/pdf"
        assert markdown.original_filename == "guide.markdown"
        assert text.size == 5

    asyncio.run(scenario())


def test_rejects_mismatch_fake_pdf_invalid_text_and_traversal() -> None:
    async def scenario() -> None:
        with pytest.raises(KnowledgeUploadValidationError):
            await validate_upload(
                _upload("guide.txt", "application/pdf", b"%PDF-1.7"),
                source_type="pdf",
            )
        with pytest.raises(KnowledgeUploadValidationError):
            await validate_upload(
                _upload("malware.pdf", "application/pdf", b"MZ executable"),
                source_type="pdf",
            )
        with pytest.raises(KnowledgeUploadValidationError):
            await validate_upload(
                _upload("bad.txt", "text/plain", b"\xff\xfe\xfa"),
                source_type="text",
            )
        validated = await validate_upload(
            _upload("../../safe.txt", "text/plain", b"safe"),
            source_type="text",
        )
        assert validated.original_filename == "safe.txt"

    asyncio.run(scenario())


def test_rejects_oversized_text_without_unbounded_read() -> None:
    async def scenario() -> None:
        with pytest.raises(KnowledgeUploadTooLargeError):
            await validate_upload(
                _upload("large.txt", "text/plain", b"x" * (5 * 1024 * 1024 + 1)),
                source_type="text",
            )

    asyncio.run(scenario())
