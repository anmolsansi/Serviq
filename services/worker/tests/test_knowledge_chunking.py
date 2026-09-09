from __future__ import annotations

import pytest

from app.core.knowledge_chunking import (
    ChunkPolicy,
    ChunkProvenance,
    KnowledgeChunkingError,
    KnowledgeChunkingErrorCode,
    chunk_normalized_segments,
)
from app.core.knowledge_normalization import NormalizedSegment


def _tokens(start: int, stop: int) -> str:
    return " ".join(f"t{index}" for index in range(start, stop))


def test_short_input_creates_one_chunk_with_token_count_and_provenance() -> None:
    segments = (
        NormalizedSegment(
            ordinal=0,
            text="alpha beta gamma",
            start_line=1,
            end_line=1,
        ),
    )

    chunks = chunk_normalized_segments(segments)

    assert len(chunks) == 1
    assert chunks[0].ordinal == 0
    assert chunks[0].text == "alpha beta gamma"
    assert chunks[0].token_count == 3
    assert chunks[0].heading_path == ()
    assert chunks[0].provenance == (
        ChunkProvenance(
            segment_ordinal=0,
            page_number=None,
            heading_path=(),
            start_line=1,
            end_line=1,
        ),
    )


def test_long_group_uses_bounded_windows_with_exact_overlap() -> None:
    segments = (
        NormalizedSegment(
            ordinal=0,
            text=_tokens(0, 900),
            heading_path=("Guide",),
        ),
    )

    chunks = chunk_normalized_segments(segments)

    assert [chunk.token_count for chunk in chunks] == [512, 452]
    assert all(chunk.token_count <= 512 for chunk in chunks)
    assert all(chunk.text for chunk in chunks)
    first_tokens = chunks[0].text.split()
    second_tokens = chunks[1].text.split()
    assert first_tokens[-64:] == second_tokens[:64]
    assert second_tokens[0] == "t448"
    assert second_tokens[-1] == "t899"


def test_heading_changes_create_groups_and_leading_title_attaches_to_first_heading() -> None:
    segments = (
        NormalizedSegment(ordinal=0, text="Help & Support"),
        NormalizedSegment(ordinal=1, text="Returns", heading_path=("Returns",)),
        NormalizedSegment(ordinal=2, text="Read carefully", heading_path=("Returns",)),
        NormalizedSegment(
            ordinal=3,
            text="Steps",
            heading_path=("Returns", "Steps"),
        ),
        NormalizedSegment(
            ordinal=4,
            text="Open orders",
            heading_path=("Returns", "Steps"),
        ),
    )

    chunks = chunk_normalized_segments(segments)

    assert [chunk.heading_path for chunk in chunks] == [
        ("Returns",),
        ("Returns", "Steps"),
    ]
    assert chunks[0].text == "Help & Support\n\nReturns\n\nRead carefully"
    assert [item.segment_ordinal for item in chunks[0].provenance] == [0, 1, 2]
    assert chunks[1].text == "Steps\n\nOpen orders"
    assert [item.segment_ordinal for item in chunks[1].provenance] == [3, 4]


def test_list_segments_preserve_source_order_and_provenance() -> None:
    heading = ("Guide", "Steps")
    segments = (
        NormalizedSegment(ordinal=0, text="Steps", heading_path=heading),
        NormalizedSegment(ordinal=1, text="Open orders", heading_path=heading),
        NormalizedSegment(ordinal=2, text="Choose an item", heading_path=heading),
    )

    chunk = chunk_normalized_segments(segments)[0]

    assert chunk.text == "Steps\n\nOpen orders\n\nChoose an item"
    assert [item.segment_ordinal for item in chunk.provenance] == [0, 1, 2]


def test_exact_token_boundary_and_one_token_over_boundary_are_deterministic() -> None:
    exact = chunk_normalized_segments(
        (NormalizedSegment(ordinal=0, text=_tokens(0, 512)),)
    )
    over = chunk_normalized_segments(
        (NormalizedSegment(ordinal=0, text=_tokens(0, 513)),)
    )

    assert [chunk.token_count for chunk in exact] == [512]
    assert [chunk.token_count for chunk in over] == [512, 65]
    assert over[1].text.split()[0] == "t448"
    assert over[0].text.split()[-64:] == over[1].text.split()[:64]


def test_repeated_identical_input_produces_identical_chunks() -> None:
    segments = (
        NormalizedSegment(ordinal=0, text="Guide", heading_path=("Guide",)),
        NormalizedSegment(ordinal=1, text=_tokens(0, 700), heading_path=("Guide",)),
    )

    assert chunk_normalized_segments(segments) == chunk_normalized_segments(segments)


def test_provenance_preserves_existing_page_and_line_metadata() -> None:
    segments = (
        NormalizedSegment(
            ordinal=0,
            text="Page content",
            page_number=2,
            heading_path=("Guide",),
        ),
        NormalizedSegment(
            ordinal=1,
            text="Line content",
            heading_path=("Guide",),
            start_line=10,
            end_line=12,
        ),
    )

    provenance = chunk_normalized_segments(segments)[0].provenance

    assert provenance[0].page_number == 2
    assert provenance[0].start_line is None
    assert provenance[1].page_number is None
    assert (provenance[1].start_line, provenance[1].end_line) == (10, 12)


def test_empty_input_fails_safely() -> None:
    with pytest.raises(KnowledgeChunkingError) as exc_info:
        chunk_normalized_segments(())

    assert exc_info.value.code == KnowledgeChunkingErrorCode.EMPTY_INPUT


def test_noncontiguous_or_wrong_type_input_fails_instead_of_being_repaired() -> None:
    with pytest.raises(KnowledgeChunkingError) as noncontiguous:
        chunk_normalized_segments((NormalizedSegment(ordinal=1, text="content"),))
    assert noncontiguous.value.code == KnowledgeChunkingErrorCode.INVALID_SEGMENTS

    with pytest.raises(KnowledgeChunkingError) as wrong_type:
        chunk_normalized_segments((object(),))  # type: ignore[arg-type]
    assert wrong_type.value.code == KnowledgeChunkingErrorCode.INVALID_SEGMENTS


def test_token_empty_segment_fails_without_raw_content_leakage(
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw = "\u2003\u2003\t\n"

    with pytest.raises(KnowledgeChunkingError) as exc_info:
        chunk_normalized_segments((NormalizedSegment(ordinal=0, text=raw),))

    assert exc_info.value.code == KnowledgeChunkingErrorCode.TOKEN_EMPTY_SEGMENT
    assert raw not in str(exc_info.value)
    assert raw not in caplog.text


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_tokens": 0},
        {"max_tokens": True},
        {"overlap_tokens": -1},
        {"overlap_tokens": 512},
        {"max_chunks": 0},
    ],
)
def test_invalid_policy_values_are_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(KnowledgeChunkingError) as exc_info:
        ChunkPolicy(**kwargs)  # type: ignore[arg-type]

    assert exc_info.value.code == KnowledgeChunkingErrorCode.INVALID_POLICY


def test_max_chunks_is_enforced_deterministically() -> None:
    policy = ChunkPolicy(max_tokens=2, overlap_tokens=1, max_chunks=1)

    with pytest.raises(KnowledgeChunkingError) as exc_info:
        chunk_normalized_segments(
            (NormalizedSegment(ordinal=0, text="one two three"),),
            policy,
        )

    assert exc_info.value.code == KnowledgeChunkingErrorCode.CHUNK_LIMIT_EXCEEDED
