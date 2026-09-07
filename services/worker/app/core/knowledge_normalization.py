"""Deterministic, bounded normalization for untrusted knowledge content."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from html.parser import HTMLParser
from io import BytesIO
from typing import Literal

from pypdf import PdfReader
from pypdf.errors import LimitReachedError, PdfReadError, PdfStreamError

KnowledgeSourceType = Literal["pdf", "markdown", "text", "url"]

_MIB = 1024 * 1024
_ATX_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_LIST_MARKER = re.compile(r"^[ \t]*(?:[-+*]|\d+[.)])[ \t]+")
_BLOCKQUOTE_MARKER = re.compile(r"^[ \t]*(?:>[ \t]?)+")
_AUTOLINK = re.compile(r"<((?:https?://|mailto:)[^>\s]+)>")
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_HTML_TAG = re.compile(r"<[^>\n]{1,1024}>")
_INLINE_CODE = re.compile(r"`+([^`\n]+?)`+")
_MARKDOWN_ESCAPE = re.compile(r"\\([\\`*_[\]{}()#+.!>~-])")
_EMPHASIS_MARKER = re.compile(r"(?<!\w)[*_](?=\S)|(?<=\S)[*_](?!\w)")
_HORIZONTAL_SPACE = re.compile(r"[ \t\f\v]+")
_HTML_SPACE = re.compile(r"[ \t\r\n\f\v]+")
_HTML_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_HTML_IGNORED_SUBTREES = frozenset(
    {
        "script",
        "style",
        "form",
        "nav",
        "noscript",
        "template",
        "svg",
        "canvas",
        "iframe",
        "object",
        "embed",
        "header",
        "footer",
        "aside",
    }
)
_HTML_VOID_IGNORED = frozenset({"embed"})
HtmlScope = Literal["article", "main", "fallback"]
HtmlCandidateKind = Literal["heading", "content"]
HtmlCaptureKind = Literal["title", "heading", "content"]


class KnowledgeNormalizationErrorCode(StrEnum):
    SOURCE_TYPE_UNSUPPORTED = "KNOWLEDGE_NORMALIZATION_SOURCE_TYPE_UNSUPPORTED"
    INPUT_TOO_LARGE = "KNOWLEDGE_NORMALIZATION_INPUT_TOO_LARGE"
    INVALID_UTF8 = "KNOWLEDGE_NORMALIZATION_INVALID_UTF8"
    TEXT_INVALID = "KNOWLEDGE_NORMALIZATION_TEXT_INVALID"
    PDF_MALFORMED = "KNOWLEDGE_NORMALIZATION_PDF_MALFORMED"
    PDF_ENCRYPTED = "KNOWLEDGE_NORMALIZATION_PDF_ENCRYPTED"
    PDF_PAGE_LIMIT_EXCEEDED = "KNOWLEDGE_NORMALIZATION_PDF_PAGE_LIMIT_EXCEEDED"
    HTML_MALFORMED = "KNOWLEDGE_NORMALIZATION_HTML_MALFORMED"
    OUTPUT_TOO_LARGE = "KNOWLEDGE_NORMALIZATION_OUTPUT_TOO_LARGE"
    SEGMENT_LIMIT_EXCEEDED = "KNOWLEDGE_NORMALIZATION_SEGMENT_LIMIT_EXCEEDED"
    EMPTY_CONTENT = "KNOWLEDGE_NORMALIZATION_EMPTY_CONTENT"


_ERROR_MESSAGES: dict[KnowledgeNormalizationErrorCode, str] = {
    KnowledgeNormalizationErrorCode.SOURCE_TYPE_UNSUPPORTED: (
        "Knowledge source type is unsupported."
    ),
    KnowledgeNormalizationErrorCode.INPUT_TOO_LARGE: (
        "Knowledge input exceeds the normalization limit."
    ),
    KnowledgeNormalizationErrorCode.INVALID_UTF8: "Knowledge text must be valid UTF-8.",
    KnowledgeNormalizationErrorCode.TEXT_INVALID: "Knowledge text content is invalid.",
    KnowledgeNormalizationErrorCode.PDF_MALFORMED: (
        "Knowledge PDF is malformed or unsupported."
    ),
    KnowledgeNormalizationErrorCode.PDF_ENCRYPTED: (
        "Encrypted knowledge PDFs are not supported."
    ),
    KnowledgeNormalizationErrorCode.PDF_PAGE_LIMIT_EXCEEDED: (
        "Knowledge PDF exceeds the page limit."
    ),
    KnowledgeNormalizationErrorCode.HTML_MALFORMED: (
        "Knowledge HTML is malformed or unsupported."
    ),
    KnowledgeNormalizationErrorCode.OUTPUT_TOO_LARGE: (
        "Normalized knowledge output exceeds the limit."
    ),
    KnowledgeNormalizationErrorCode.SEGMENT_LIMIT_EXCEEDED: (
        "Normalized knowledge has too many segments."
    ),
    KnowledgeNormalizationErrorCode.EMPTY_CONTENT: (
        "Knowledge content contains no extractable text."
    ),
}


class KnowledgeNormalizationError(ValueError):
    """Safe parser failure containing only a stable code and generic message."""

    def __init__(self, code: KnowledgeNormalizationErrorCode) -> None:
        self.code = code
        super().__init__(_ERROR_MESSAGES[code])


@dataclass(frozen=True, slots=True)
class NormalizationLimits:
    max_pdf_bytes: int = 25 * _MIB
    max_text_bytes: int = 5 * _MIB
    max_pdf_pages: int = 2_000
    max_total_chars: int = 5 * _MIB
    max_segment_chars: int = 32_768
    max_segments: int = 20_000

    def __post_init__(self) -> None:
        values = (
            self.max_pdf_bytes,
            self.max_text_bytes,
            self.max_pdf_pages,
            self.max_total_chars,
            self.max_segment_chars,
            self.max_segments,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in values
        ):
            raise ValueError("Normalization limits must be positive integers.")


DEFAULT_NORMALIZATION_LIMITS = NormalizationLimits()


@dataclass(frozen=True, slots=True)
class NormalizedSegment:
    ordinal: int
    text: str
    page_number: int | None = None
    heading_path: tuple[str, ...] = ()
    start_line: int | None = None
    end_line: int | None = None


@dataclass(frozen=True, slots=True)
class _Block:
    text: str
    page_number: int | None = None
    heading_path: tuple[str, ...] = ()
    start_line: int | None = None
    end_line: int | None = None


@dataclass(frozen=True, slots=True)
class _HtmlCandidate:
    kind: HtmlCandidateKind
    text: str
    scope: HtmlScope
    heading_level: int | None = None


@dataclass(slots=True)
class _HtmlCapture:
    tag: str
    kind: HtmlCaptureKind
    scope: HtmlScope
    heading_level: int | None
    parts: list[str | None]


class _KnowledgeHtmlParser(HTMLParser):
    """Collect HTML text candidates without rendering or executing content."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.titles: list[str] = []
        self.candidates: list[_HtmlCandidate] = []
        self._capture: _HtmlCapture | None = None
        self._skip_stack: list[str] = []
        self._article_depth = 0
        self._main_depth = 0
        self._body_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if (
            self._skip_stack
            and tag in _HTML_IGNORED_SUBTREES
            and tag not in _HTML_VOID_IGNORED
        ):
            self._skip_stack.append(tag)
            return
        if self._skip_stack:
            return
        if tag in _HTML_IGNORED_SUBTREES and tag not in _HTML_VOID_IGNORED:
            self._skip_stack.append(tag)
            return
        if tag in _HTML_IGNORED_SUBTREES:
            return

        if tag == "article":
            self._article_depth += 1
            return
        if tag == "main":
            self._main_depth += 1
            return
        if tag == "body":
            self._body_depth += 1
            return
        if tag == "br" and self._capture is not None:
            self._capture.parts.append(None)
            return
        if tag == "br":
            return
        if self._capture is not None:
            return

        if tag == "title":
            self._capture = _HtmlCapture(
                tag=tag,
                kind="title",
                scope="fallback",
                heading_level=None,
                parts=[],
            )
            return
        if tag in _HTML_HEADING_TAGS:
            self._capture = _HtmlCapture(
                tag=tag,
                kind="heading",
                scope=self._current_scope(),
                heading_level=int(tag[1]),
                parts=[],
            )
            return
        if tag in {"p", "li"}:
            self._capture = _HtmlCapture(
                tag=tag,
                kind="content",
                scope=self._current_scope(),
                heading_level=None,
                parts=[],
            )

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        tag = tag.lower()
        if self._skip_stack or tag in _HTML_IGNORED_SUBTREES:
            return
        if tag == "br" and self._capture is not None:
            self._capture.parts.append(None)
            return
        if tag == "br":
            return
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._skip_stack:
            if tag == self._skip_stack[-1]:
                self._skip_stack.pop()
            return

        if self._capture is not None and tag == self._capture.tag:
            self._finish_capture()

        if tag == "article" and self._article_depth > 0:
            self._article_depth -= 1
        elif tag == "main" and self._main_depth > 0:
            self._main_depth -= 1
        elif tag == "body" and self._body_depth > 0:
            self._body_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_stack and self._capture is not None:
            self._capture.parts.append(data)

    def finish(self) -> None:
        """Flush one unclosed eligible capture after HTMLParser.close()."""

        if self._capture is not None and not self._skip_stack:
            self._finish_capture()

    def _current_scope(self) -> HtmlScope:
        if self._article_depth > 0:
            return "article"
        if self._main_depth > 0:
            return "main"
        return "fallback"

    def _finish_capture(self) -> None:
        capture = self._capture
        self._capture = None
        if capture is None:
            return
        text = _clean_html_parts(capture.parts)
        if not text:
            return
        if capture.kind == "title":
            self.titles.append(text)
            return
        kind: HtmlCandidateKind = "heading" if capture.kind == "heading" else "content"
        self.candidates.append(
            _HtmlCandidate(
                kind=kind,
                text=text,
                scope=capture.scope,
                heading_level=capture.heading_level,
            )
        )


def normalize_knowledge_content(
    raw_bytes: bytes,
    source_type: str,
    limits: NormalizationLimits = DEFAULT_NORMALIZATION_LIMITS,
) -> tuple[NormalizedSegment, ...]:
    """Normalize untrusted knowledge bytes without executing embedded content."""

    if source_type not in {"pdf", "markdown", "text", "url"}:
        raise KnowledgeNormalizationError(
            KnowledgeNormalizationErrorCode.SOURCE_TYPE_UNSUPPORTED
        )
    if not isinstance(raw_bytes, bytes):
        raise KnowledgeNormalizationError(KnowledgeNormalizationErrorCode.TEXT_INVALID)

    maximum = limits.max_pdf_bytes if source_type == "pdf" else limits.max_text_bytes
    if len(raw_bytes) > maximum:
        raise KnowledgeNormalizationError(KnowledgeNormalizationErrorCode.INPUT_TOO_LARGE)

    if source_type == "pdf":
        blocks = _normalize_pdf(raw_bytes, limits)
    else:
        decoded = _decode_text(raw_bytes)
        if source_type == "markdown":
            blocks = _normalize_markdown(decoded)
        elif source_type == "url":
            blocks = _normalize_html(decoded)
        else:
            blocks = _normalize_plain_text(decoded)
    return _materialize_segments(blocks, limits)


def _decode_text(raw_bytes: bytes) -> str:
    if b"\x00" in raw_bytes:
        raise KnowledgeNormalizationError(KnowledgeNormalizationErrorCode.TEXT_INVALID)
    try:
        return raw_bytes.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError:
        raise KnowledgeNormalizationError(KnowledgeNormalizationErrorCode.INVALID_UTF8) from None


def _normalize_plain_text(text: str) -> list[_Block]:
    return _blocks_from_lines(_normalized_lines(text), clean_line=_plain_line)


def _normalize_markdown(text: str) -> list[_Block]:
    lines = _normalized_lines(text)
    blocks: list[_Block] = []
    pending: list[tuple[int, str]] = []
    headings: list[str] = []
    in_fence = False

    def flush_pending() -> None:
        if not pending:
            return
        block_text = "\n".join(value for _, value in pending).strip()
        if block_text:
            blocks.append(
                _Block(
                    text=block_text,
                    heading_path=tuple(headings),
                    start_line=pending[0][0],
                    end_line=pending[-1][0],
                )
            )
        pending.clear()

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            flush_pending()
            in_fence = not in_fence
            continue
        if not in_fence:
            heading = _ATX_HEADING.match(line)
            if heading is not None:
                flush_pending()
                level = len(heading.group(1))
                title = _clean_markdown_inline(heading.group(2))
                if not title:
                    continue
                headings[:] = headings[: level - 1]
                while len(headings) < level - 1:
                    headings.append("")
                headings.append(title)
                heading_path = tuple(item for item in headings if item)
                blocks.append(
                    _Block(
                        text=title,
                        heading_path=heading_path,
                        start_line=line_number,
                        end_line=line_number,
                    )
                )
                continue
        if not stripped:
            flush_pending()
            continue
        cleaned = line.strip() if in_fence else _clean_markdown_line(line)
        if cleaned:
            pending.append((line_number, cleaned))
    flush_pending()
    return blocks



def _normalize_html(text: str) -> list[_Block]:
    try:
        parser = _KnowledgeHtmlParser()
        parser.feed(text)
        parser.close()
        parser.finish()
        return _html_blocks(parser)
    except Exception:
        raise KnowledgeNormalizationError(
            KnowledgeNormalizationErrorCode.HTML_MALFORMED
        ) from None


def _html_blocks(parser: _KnowledgeHtmlParser) -> list[_Block]:
    article = [candidate for candidate in parser.candidates if candidate.scope == "article"]
    main = [candidate for candidate in parser.candidates if candidate.scope == "main"]
    fallback = [
        candidate for candidate in parser.candidates if candidate.scope == "fallback"
    ]
    selected = article or main or fallback

    blocks: list[_Block] = []
    if parser.titles:
        blocks.append(_Block(text=parser.titles[0]))

    headings: list[str] = []
    for candidate in selected:
        if candidate.kind == "heading":
            level = candidate.heading_level
            if level is None:
                continue
            headings[:] = headings[: level - 1]
            while len(headings) < level - 1:
                headings.append("")
            headings.append(candidate.text)
            heading_path = tuple(item for item in headings if item)
            blocks.append(_Block(text=candidate.text, heading_path=heading_path))
            continue
        blocks.append(
            _Block(
                text=candidate.text,
                heading_path=tuple(item for item in headings if item),
            )
        )
    return blocks


def _clean_html_parts(parts: list[str | None]) -> str:
    lines: list[str] = []
    pending: list[str] = []
    for part in parts:
        if part is None:
            lines.append(_HTML_SPACE.sub(" ", "".join(pending)).strip())
            pending = []
            continue
        pending.append(part)
    lines.append(_HTML_SPACE.sub(" ", "".join(pending)).strip())

    start = 0
    while start < len(lines) and not lines[start]:
        start += 1
    end = len(lines)
    while end > start and not lines[end - 1]:
        end -= 1
    return "\n".join(lines[start:end])


def _normalize_pdf(raw_bytes: bytes, limits: NormalizationLimits) -> list[_Block]:
    try:
        reader = PdfReader(BytesIO(raw_bytes), strict=True)
        if reader.is_encrypted:
            raise KnowledgeNormalizationError(KnowledgeNormalizationErrorCode.PDF_ENCRYPTED)
        if len(reader.pages) > limits.max_pdf_pages:
            raise KnowledgeNormalizationError(
                KnowledgeNormalizationErrorCode.PDF_PAGE_LIMIT_EXCEEDED
            )
        blocks: list[_Block] = []
        for page_number, page in enumerate(reader.pages, start=1):
            extracted = page.extract_text()
            page_blocks = _blocks_from_lines(
                _normalized_lines(extracted), clean_line=_plain_line
            )
            blocks.extend(
                _Block(text=block.text, page_number=page_number) for block in page_blocks
            )
        return blocks
    except KnowledgeNormalizationError:
        raise
    except (
        PdfReadError,
        PdfStreamError,
        LimitReachedError,
        ValueError,
        TypeError,
        KeyError,
        AssertionError,
        RecursionError,
    ):
        raise KnowledgeNormalizationError(
            KnowledgeNormalizationErrorCode.PDF_MALFORMED
        ) from None


def _normalized_lines(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return [line.rstrip(" \t\f\v") for line in normalized.split("\n")]


def _plain_line(line: str) -> str:
    return _HORIZONTAL_SPACE.sub(" ", line.strip())


def _clean_markdown_line(line: str) -> str:
    value = _BLOCKQUOTE_MARKER.sub("", line)
    value = _LIST_MARKER.sub("", value)
    return _clean_markdown_inline(value)


def _clean_markdown_inline(value: str) -> str:
    value = _AUTOLINK.sub(r"\1", value)
    value = _IMAGE.sub(r"\1", value)
    value = _LINK.sub(r"\1", value)
    value = _INLINE_CODE.sub(r"\1", value)
    value = _HTML_TAG.sub("", value)
    value = _MARKDOWN_ESCAPE.sub(r"\1", value)
    value = value.replace("**", "").replace("__", "").replace("~~", "")
    value = _EMPHASIS_MARKER.sub("", value)
    return _HORIZONTAL_SPACE.sub(" ", value.strip())


def _blocks_from_lines(
    lines: list[str], *, clean_line: Callable[[str], str]
) -> list[_Block]:
    blocks: list[_Block] = []
    pending: list[tuple[int, str]] = []
    for line_number, line in enumerate(lines, start=1):
        cleaned = clean_line(line)
        if cleaned:
            pending.append((line_number, cleaned))
            continue
        if pending:
            blocks.append(_pending_block(pending))
            pending = []
    if pending:
        blocks.append(_pending_block(pending))
    return blocks


def _pending_block(pending: list[tuple[int, str]]) -> _Block:
    return _Block(
        text="\n".join(value for _, value in pending).strip(),
        start_line=pending[0][0],
        end_line=pending[-1][0],
    )


def _materialize_segments(
    blocks: list[_Block], limits: NormalizationLimits
) -> tuple[NormalizedSegment, ...]:
    segments: list[NormalizedSegment] = []
    total_chars = 0
    for block in blocks:
        for piece in _split_text(block.text, limits.max_segment_chars):
            total_chars += len(piece)
            if total_chars > limits.max_total_chars:
                raise KnowledgeNormalizationError(
                    KnowledgeNormalizationErrorCode.OUTPUT_TOO_LARGE
                )
            if len(segments) >= limits.max_segments:
                raise KnowledgeNormalizationError(
                    KnowledgeNormalizationErrorCode.SEGMENT_LIMIT_EXCEEDED
                )
            segments.append(
                NormalizedSegment(
                    ordinal=len(segments),
                    text=piece,
                    page_number=block.page_number,
                    heading_path=block.heading_path,
                    start_line=block.start_line,
                    end_line=block.end_line,
                )
            )
    if not segments:
        raise KnowledgeNormalizationError(KnowledgeNormalizationErrorCode.EMPTY_CONTENT)
    return tuple(segments)


def _split_text(text: str, maximum: int) -> list[str]:
    remaining = text.strip()
    pieces: list[str] = []
    while len(remaining) > maximum:
        boundary = remaining.rfind("\n", 0, maximum + 1)
        if boundary <= 0:
            boundary = remaining.rfind(" ", 0, maximum + 1)
        if boundary <= 0:
            boundary = maximum
        piece = remaining[:boundary].strip()
        if piece:
            pieces.append(piece)
        remaining = remaining[boundary:].lstrip()
    if remaining:
        pieces.append(remaining)
    return pieces
