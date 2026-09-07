from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.core.knowledge_normalization import (
    KnowledgeNormalizationError,
    KnowledgeNormalizationErrorCode,
    NormalizationLimits,
    normalize_knowledge_content,
)


def test_text_normalization_preserves_blocks_and_line_provenance() -> None:
    segments = normalize_knowledge_content(
        b" first   line  \r\nsecond line\r\n\r\nthird\tline ", "text"
    )

    assert [segment.text for segment in segments] == [
        "first line\nsecond line",
        "third line",
    ]
    assert [(segment.start_line, segment.end_line) for segment in segments] == [
        (1, 2),
        (4, 4),
    ]
    assert all(segment.page_number is None for segment in segments)
    assert all(segment.heading_path == () for segment in segments)


def test_text_accepts_utf8_bom_and_rejects_invalid_utf8_and_nul() -> None:
    assert normalize_knowledge_content(b"\xef\xbb\xbfhello", "text")[0].text == "hello"

    with pytest.raises(KnowledgeNormalizationError) as invalid_utf8:
        normalize_knowledge_content(b"hello\xff", "text")
    assert invalid_utf8.value.code == KnowledgeNormalizationErrorCode.INVALID_UTF8

    with pytest.raises(KnowledgeNormalizationError) as nul:
        normalize_knowledge_content(b"hello\x00world", "text")
    assert nul.value.code == KnowledgeNormalizationErrorCode.TEXT_INVALID


def test_markdown_tracks_headings_and_emits_inert_plain_text() -> None:
    markdown = b"""# Guide
Intro with **bold**, [docs](https://example.com), and `code`.

## Steps
- first item
> second item

```python
print(\"never execute\")
```

### Details
![diagram](https://example.com/image.png) <span>safe text</span>
"""

    segments = normalize_knowledge_content(markdown, "markdown")

    assert [segment.text for segment in segments] == [
        "Guide",
        "Intro with bold, docs, and code.",
        "Steps",
        "first item\nsecond item",
        'print("never execute")',
        "Details",
        "diagram safe text",
    ]
    assert [segment.heading_path for segment in segments] == [
        ("Guide",),
        ("Guide",),
        ("Guide", "Steps"),
        ("Guide", "Steps"),
        ("Guide", "Steps"),
        ("Guide", "Steps", "Details"),
        ("Guide", "Steps", "Details"),
    ]
    assert [(segment.start_line, segment.end_line) for segment in segments] == [
        (1, 1),
        (2, 2),
        (4, 4),
        (5, 6),
        (9, 9),
        (12, 12),
        (13, 13),
    ]


def test_normalization_is_deterministic() -> None:
    raw = b"# One\nalpha beta\n\n## Two\ngamma"

    first = normalize_knowledge_content(raw, "markdown")
    second = normalize_knowledge_content(raw, "markdown")

    assert first == second


def test_pdf_extracts_multiple_pages_with_one_based_provenance() -> None:
    pdf = _text_pdf(["Page one", "Page two"])

    segments = normalize_knowledge_content(pdf, "pdf")

    assert [segment.text for segment in segments] == ["Page one", "Page two"]
    assert [segment.page_number for segment in segments] == [1, 2]
    assert all(segment.start_line is None for segment in segments)
    assert all(segment.end_line is None for segment in segments)


def test_pdf_skips_blank_pages_and_never_falls_back_to_ocr() -> None:
    mixed = normalize_knowledge_content(_text_pdf(["", "Visible text"]), "pdf")
    assert [segment.text for segment in mixed] == ["Visible text"]
    assert [segment.page_number for segment in mixed] == [2]

    with pytest.raises(KnowledgeNormalizationError) as empty:
        normalize_knowledge_content(_text_pdf([""]), "pdf")
    assert empty.value.code == KnowledgeNormalizationErrorCode.EMPTY_CONTENT


def test_malformed_pdf_fails_with_safe_code() -> None:
    with pytest.raises(KnowledgeNormalizationError) as exc_info:
        normalize_knowledge_content(b"%PDF-1.4\nnot-a-valid-pdf", "pdf")

    assert exc_info.value.code == KnowledgeNormalizationErrorCode.PDF_MALFORMED
    assert str(exc_info.value) == "Knowledge PDF is malformed or unsupported."


def test_encrypted_pdf_is_rejected_without_decryption() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("secret", algorithm="RC4-128")
    output = BytesIO()
    writer.write(output)

    with pytest.raises(KnowledgeNormalizationError) as exc_info:
        normalize_knowledge_content(output.getvalue(), "pdf")

    assert exc_info.value.code == KnowledgeNormalizationErrorCode.PDF_ENCRYPTED


def test_input_and_pdf_page_limits_are_enforced() -> None:
    tiny = NormalizationLimits(
        max_pdf_bytes=1_000_000,
        max_text_bytes=4,
        max_pdf_pages=1,
        max_total_chars=1_000,
        max_segment_chars=100,
        max_segments=100,
    )

    with pytest.raises(KnowledgeNormalizationError) as too_large:
        normalize_knowledge_content(b"12345", "text", tiny)
    assert too_large.value.code == KnowledgeNormalizationErrorCode.INPUT_TOO_LARGE

    with pytest.raises(KnowledgeNormalizationError) as too_many_pages:
        normalize_knowledge_content(_text_pdf(["one", "two"]), "pdf", tiny)
    assert too_many_pages.value.code == KnowledgeNormalizationErrorCode.PDF_PAGE_LIMIT_EXCEEDED


def test_segment_splitting_and_output_bounds_are_deterministic() -> None:
    split_limits = NormalizationLimits(
        max_pdf_bytes=1_000,
        max_text_bytes=1_000,
        max_pdf_pages=10,
        max_total_chars=100,
        max_segment_chars=6,
        max_segments=10,
    )
    segments = normalize_knowledge_content(b"alpha beta gamma", "text", split_limits)
    assert [segment.text for segment in segments] == ["alpha", "beta", "gamma"]
    assert [segment.ordinal for segment in segments] == [0, 1, 2]

    output_limits = NormalizationLimits(
        max_pdf_bytes=1_000,
        max_text_bytes=1_000,
        max_pdf_pages=10,
        max_total_chars=4,
        max_segment_chars=10,
        max_segments=10,
    )
    with pytest.raises(KnowledgeNormalizationError) as output_too_large:
        normalize_knowledge_content(b"abcde", "text", output_limits)
    assert output_too_large.value.code == KnowledgeNormalizationErrorCode.OUTPUT_TOO_LARGE

    segment_limits = NormalizationLimits(
        max_pdf_bytes=1_000,
        max_text_bytes=1_000,
        max_pdf_pages=10,
        max_total_chars=100,
        max_segment_chars=10,
        max_segments=1,
    )
    with pytest.raises(KnowledgeNormalizationError) as too_many_segments:
        normalize_knowledge_content(b"one\n\ntwo", "text", segment_limits)
    assert too_many_segments.value.code == KnowledgeNormalizationErrorCode.SEGMENT_LIMIT_EXCEEDED


def test_empty_and_unsupported_content_fail_safely() -> None:
    with pytest.raises(KnowledgeNormalizationError) as empty:
        normalize_knowledge_content(b"  \n\n\t", "text")
    assert empty.value.code == KnowledgeNormalizationErrorCode.EMPTY_CONTENT

    with pytest.raises(KnowledgeNormalizationError) as unsupported:
        normalize_knowledge_content(b"content", "url")
    assert unsupported.value.code == KnowledgeNormalizationErrorCode.SOURCE_TYPE_UNSUPPORTED


def test_raw_sensitive_content_never_appears_in_parser_error_or_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = "SECRET-DOCUMENT-CONTENT-9f3a"
    raw = ("%PDF-1.4\n" + sentinel).encode()

    with pytest.raises(KnowledgeNormalizationError) as exc_info:
        normalize_knowledge_content(raw, "pdf")

    assert sentinel not in str(exc_info.value)
    assert sentinel not in caplog.text


def _text_pdf(page_texts: list[str]) -> bytes:
    """Build a tiny deterministic PDF fixture without adding a test-only dependency."""

    page_object_numbers = [4 + (index * 2) for index in range(len(page_texts))]
    content_object_numbers = [number + 1 for number in page_object_numbers]
    kids = " ".join(f"{number} 0 R" for number in page_object_numbers)
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{kids}] /Count {len(page_texts)} >>".encode(),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }

    for page_number, text in enumerate(page_texts):
        page_object = page_object_numbers[page_number]
        content_object = content_object_numbers[page_number]
        objects[page_object] = (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_object} 0 R >>"
        ).encode()
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode()
        objects[content_object] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode()
            + stream
            + b"\nendstream"
        )

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_number in range(1, max(objects) + 1):
        offsets.append(len(output))
        output.extend(f"{object_number} 0 obj\n".encode())
        output.extend(objects[object_number])
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    return bytes(output)
