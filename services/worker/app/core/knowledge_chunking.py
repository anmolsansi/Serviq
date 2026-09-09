"""Deterministic, bounded chunking for normalized knowledge content."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.core.knowledge_normalization import NormalizedSegment

_TOKEN = re.compile(r"\S+")
_GROUP_SEPARATOR = "\n\n"


class KnowledgeChunkingErrorCode(StrEnum):
    EMPTY_INPUT = "KNOWLEDGE_CHUNKING_EMPTY_INPUT"
    INVALID_SEGMENTS = "KNOWLEDGE_CHUNKING_INVALID_SEGMENTS"
    TOKEN_EMPTY_SEGMENT = "KNOWLEDGE_CHUNKING_TOKEN_EMPTY_SEGMENT"
    INVALID_POLICY = "KNOWLEDGE_CHUNKING_INVALID_POLICY"
    CHUNK_LIMIT_EXCEEDED = "KNOWLEDGE_CHUNKING_CHUNK_LIMIT_EXCEEDED"


_ERROR_MESSAGES: dict[KnowledgeChunkingErrorCode, str] = {
    KnowledgeChunkingErrorCode.EMPTY_INPUT: "Normalized knowledge input is empty.",
    KnowledgeChunkingErrorCode.INVALID_SEGMENTS: (
        "Normalized knowledge segments are invalid or out of order."
    ),
    KnowledgeChunkingErrorCode.TOKEN_EMPTY_SEGMENT: (
        "Normalized knowledge segment contains no chunkable tokens."
    ),
    KnowledgeChunkingErrorCode.INVALID_POLICY: "Knowledge chunk policy is invalid.",
    KnowledgeChunkingErrorCode.CHUNK_LIMIT_EXCEEDED: (
        "Knowledge chunk output exceeds the chunk limit."
    ),
}


class KnowledgeChunkingError(ValueError):
    """Safe chunking failure containing only a stable code and generic message."""

    def __init__(self, code: KnowledgeChunkingErrorCode) -> None:
        self.code = code
        super().__init__(_ERROR_MESSAGES[code])


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


@dataclass(frozen=True, slots=True)
class ChunkPolicy:
    max_tokens: int = 512
    overlap_tokens: int = 64
    max_chunks: int = 20_000

    def __post_init__(self) -> None:
        if (
            not _is_positive_int(self.max_tokens)
            or not _is_nonnegative_int(self.overlap_tokens)
            or not _is_positive_int(self.max_chunks)
            or self.overlap_tokens >= self.max_tokens
        ):
            raise KnowledgeChunkingError(KnowledgeChunkingErrorCode.INVALID_POLICY)


DEFAULT_CHUNK_POLICY = ChunkPolicy()


@dataclass(frozen=True, slots=True)
class ChunkProvenance:
    segment_ordinal: int
    page_number: int | None
    heading_path: tuple[str, ...]
    start_line: int | None
    end_line: int | None


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    ordinal: int
    text: str
    token_count: int
    heading_path: tuple[str, ...]
    provenance: tuple[ChunkProvenance, ...]


@dataclass(frozen=True, slots=True)
class _HeadingGroup:
    heading_path: tuple[str, ...]
    segments: tuple[NormalizedSegment, ...]


@dataclass(frozen=True, slots=True)
class _SegmentSpan:
    segment: NormalizedSegment
    start: int
    end: int


def chunk_normalized_segments(
    segments: Sequence[NormalizedSegment],
    policy: ChunkPolicy = DEFAULT_CHUNK_POLICY,
) -> tuple[KnowledgeChunk, ...]:
    """Chunk normalized segments using the frozen deterministic V1 policy."""

    validated = _validate_segments(segments)
    chunks: list[KnowledgeChunk] = []

    for group in _heading_groups(validated):
        group_text, segment_spans = _materialize_group(group.segments)
        token_spans = tuple(_TOKEN.finditer(group_text))
        if not token_spans:
            raise KnowledgeChunkingError(KnowledgeChunkingErrorCode.TOKEN_EMPTY_SEGMENT)

        token_start = 0
        while token_start < len(token_spans):
            token_end = min(token_start + policy.max_tokens, len(token_spans))
            char_start = token_spans[token_start].start()
            char_end = token_spans[token_end - 1].end()
            chunk_text = group_text[char_start:char_end]

            if len(chunks) >= policy.max_chunks:
                raise KnowledgeChunkingError(
                    KnowledgeChunkingErrorCode.CHUNK_LIMIT_EXCEEDED
                )

            chunks.append(
                KnowledgeChunk(
                    ordinal=len(chunks),
                    text=chunk_text,
                    token_count=token_end - token_start,
                    heading_path=group.heading_path,
                    provenance=_window_provenance(
                        segment_spans,
                        char_start=char_start,
                        char_end=char_end,
                    ),
                )
            )

            if token_end == len(token_spans):
                break
            token_start = token_end - policy.overlap_tokens

    return tuple(chunks)


def _validate_segments(
    segments: Sequence[NormalizedSegment],
) -> tuple[NormalizedSegment, ...]:
    try:
        materialized = tuple(segments)
    except TypeError:
        raise KnowledgeChunkingError(KnowledgeChunkingErrorCode.INVALID_SEGMENTS) from None

    if not materialized:
        raise KnowledgeChunkingError(KnowledgeChunkingErrorCode.EMPTY_INPUT)

    for expected_ordinal, segment in enumerate(materialized):
        if not isinstance(segment, NormalizedSegment) or segment.ordinal != expected_ordinal:
            raise KnowledgeChunkingError(KnowledgeChunkingErrorCode.INVALID_SEGMENTS)
        if _TOKEN.search(segment.text) is None:
            raise KnowledgeChunkingError(KnowledgeChunkingErrorCode.TOKEN_EMPTY_SEGMENT)

    return materialized


def _heading_groups(segments: tuple[NormalizedSegment, ...]) -> tuple[_HeadingGroup, ...]:
    first_heading_index = next(
        (index for index, segment in enumerate(segments) if segment.heading_path),
        None,
    )
    if first_heading_index is None:
        return (_HeadingGroup(heading_path=(), segments=segments),)

    groups: list[_HeadingGroup] = []
    current_path = segments[first_heading_index].heading_path
    current_segments = list(segments[: first_heading_index + 1])

    for segment in segments[first_heading_index + 1 :]:
        if segment.heading_path == current_path:
            current_segments.append(segment)
            continue
        groups.append(
            _HeadingGroup(
                heading_path=current_path,
                segments=tuple(current_segments),
            )
        )
        current_path = segment.heading_path
        current_segments = [segment]

    groups.append(
        _HeadingGroup(
            heading_path=current_path,
            segments=tuple(current_segments),
        )
    )
    return tuple(groups)


def _materialize_group(
    segments: tuple[NormalizedSegment, ...],
) -> tuple[str, tuple[_SegmentSpan, ...]]:
    text_parts: list[str] = []
    spans: list[_SegmentSpan] = []
    cursor = 0

    for index, segment in enumerate(segments):
        if index:
            text_parts.append(_GROUP_SEPARATOR)
            cursor += len(_GROUP_SEPARATOR)

        start = cursor
        text_parts.append(segment.text)
        cursor += len(segment.text)
        spans.append(_SegmentSpan(segment=segment, start=start, end=cursor))

    return "".join(text_parts), tuple(spans)


def _window_provenance(
    spans: tuple[_SegmentSpan, ...],
    *,
    char_start: int,
    char_end: int,
) -> tuple[ChunkProvenance, ...]:
    provenance: list[ChunkProvenance] = []

    for span in spans:
        if span.end <= char_start or span.start >= char_end:
            continue
        segment = span.segment
        provenance.append(
            ChunkProvenance(
                segment_ordinal=segment.ordinal,
                page_number=segment.page_number,
                heading_path=segment.heading_path,
                start_line=segment.start_line,
                end_line=segment.end_line,
            )
        )

    return tuple(provenance)
