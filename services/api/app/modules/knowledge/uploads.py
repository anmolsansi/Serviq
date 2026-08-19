"""Bounded validation for untrusted knowledge-source file uploads."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath
from typing import Literal, cast

from starlette.datastructures import UploadFile

FileKnowledgeSourceType = Literal["pdf", "markdown", "text"]

_MIB = 1024 * 1024
_CHUNK_SIZE = 64 * 1024
_RULES: dict[FileKnowledgeSourceType, tuple[frozenset[str], frozenset[str], int]] = {
    "pdf": (frozenset({".pdf"}), frozenset({"application/pdf"}), 25 * _MIB),
    "markdown": (
        frozenset({".md", ".markdown"}),
        frozenset({"text/markdown", "text/plain"}),
        5 * _MIB,
    ),
    "text": (frozenset({".txt"}), frozenset({"text/plain"}), 5 * _MIB),
}


class KnowledgeUploadValidationError(ValueError):
    """The upload does not satisfy the frozen V1 file contract."""


class KnowledgeUploadTooLargeError(KnowledgeUploadValidationError):
    """The actual uploaded file bytes exceeded the V1 maximum."""


@dataclass(frozen=True, slots=True)
class ValidatedKnowledgeUpload:
    source_type: FileKnowledgeSourceType
    content_type: str
    original_filename: str
    size: int


def parse_file_source_type(value: object) -> FileKnowledgeSourceType:
    if value not in _RULES:
        raise KnowledgeUploadValidationError("Unsupported knowledge file source type.")
    return cast(FileKnowledgeSourceType, value)


def validate_name(value: object) -> str:
    if not isinstance(value, str):
        raise KnowledgeUploadValidationError("Knowledge source name is required.")
    normalized = value.strip()
    if not 1 <= len(normalized) <= 160:
        raise KnowledgeUploadValidationError("Knowledge source name must be 1 to 160 characters.")
    return normalized


def validate_access_scope(value: object) -> Literal["customer", "internal"]:
    if value not in {"customer", "internal"}:
        raise KnowledgeUploadValidationError("Invalid knowledge source access scope.")
    return cast(Literal["customer", "internal"], value)


async def validate_upload(
    upload: UploadFile,
    *,
    source_type: FileKnowledgeSourceType,
) -> ValidatedKnowledgeUpload:
    filename = _safe_filename(upload.filename)
    extension = PurePath(filename).suffix.lower()
    allowed_extensions, allowed_mimes, maximum = _RULES[source_type]
    content_type = (upload.content_type or "").split(";", 1)[0].strip().lower()

    if extension not in allowed_extensions:
        raise KnowledgeUploadValidationError("Filename extension does not match source type.")
    if content_type not in allowed_mimes:
        raise KnowledgeUploadValidationError("Declared MIME type does not match source type.")

    size = 0
    prefix = bytearray()
    text_decoder_probe = bytearray()
    while True:
        chunk = await upload.read(_CHUNK_SIZE)
        if not chunk:
            break
        size += len(chunk)
        if size > maximum:
            raise KnowledgeUploadTooLargeError("Uploaded knowledge file exceeds the V1 limit.")
        if len(prefix) < 5:
            prefix.extend(chunk[: 5 - len(prefix)])
        if source_type != "pdf":
            text_decoder_probe.extend(chunk)

    if source_type == "pdf":
        if not bytes(prefix).startswith(b"%PDF-"):
            raise KnowledgeUploadValidationError("PDF signature check failed.")
    else:
        data = bytes(text_decoder_probe)
        if b"\x00" in data:
            raise KnowledgeUploadValidationError("Text uploads must not contain NUL bytes.")
        try:
            data.decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError:
            raise KnowledgeUploadValidationError("Text uploads must be valid UTF-8.") from None

    await upload.seek(0)
    return ValidatedKnowledgeUpload(
        source_type=source_type,
        content_type=content_type,
        original_filename=filename,
        size=size,
    )


def _safe_filename(value: str | None) -> str:
    if value is None:
        raise KnowledgeUploadValidationError("Uploaded file must have a filename.")
    normalized = value.replace("\\", "/").split("/")[-1].strip()
    normalized = "".join(
        character
        for character in normalized
        if ord(character) >= 32 and character != "\x7f"
    )
    if not normalized or len(normalized) > 255:
        raise KnowledgeUploadValidationError("Uploaded filename is invalid.")
    return normalized
