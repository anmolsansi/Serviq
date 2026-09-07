from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfWriter

import app.core.knowledge_normalization as normalization
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
        normalize_knowledge_content(b"content", "sitemap")
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



def test_html_article_extracts_title_headings_paragraphs_and_lists() -> None:
    html = b"""<html>
<head><title>Help &amp; Support</title></head>
<body>
<article>
  <h1>Returns</h1>
  <p>Read <strong>this</strong><br>carefully.</p>
  <h2>Steps</h2>
  <ul>
    <li>Open <a href="https://secret.example/orders">orders</a></li>
    <li>Choose an item</li>
  </ul>
</article>
</body>
</html>"""

    segments = normalize_knowledge_content(html, "url")

    assert [segment.text for segment in segments] == [
        "Help & Support",
        "Returns",
        "Read this\ncarefully.",
        "Steps",
        "Open orders",
        "Choose an item",
    ]
    assert [segment.heading_path for segment in segments] == [
        (),
        ("Returns",),
        ("Returns",),
        ("Returns", "Steps"),
        ("Returns", "Steps"),
        ("Returns", "Steps"),
    ]
    assert all(segment.page_number is None for segment in segments)
    assert all(segment.start_line is None for segment in segments)
    assert all(segment.end_line is None for segment in segments)
    assert "secret.example" not in " ".join(segment.text for segment in segments)


def test_html_strips_executable_form_and_navigation_noise() -> None:
    sentinel = "SECRET-HTML-NOISE-17c8"
    html = f"""<html><body>
<header><p>{sentinel}-header</p></header>
<nav><p>{sentinel}-nav</p></nav>
<main><h1>Visible</h1><p>Safe article text.</p></main>
<aside><p>{sentinel}-aside</p></aside>
<footer><p>{sentinel}-footer</p></footer>
<script>{sentinel}-script</script>
<style>.x::before {{ content: '{sentinel}-style'; }}</style>
<form><p>{sentinel}-form</p><input value="{sentinel}-value"></form>
<noscript><p>{sentinel}-noscript</p></noscript>
<template><p>{sentinel}-template</p></template>
<svg><text>{sentinel}-svg</text></svg>
<canvas>{sentinel}-canvas</canvas>
<iframe>{sentinel}-iframe</iframe>
<object>{sentinel}-object</object>
<embed src="{sentinel}-embed">
</body></html>""".encode()

    segments = normalize_knowledge_content(html, "url")

    assert [segment.text for segment in segments] == ["Visible", "Safe article text."]
    assert sentinel not in " ".join(segment.text for segment in segments)


def test_html_article_scope_wins_over_main_and_body() -> None:
    html = b"""<html><head><title>Help</title></head><body>
<h1>Body heading</h1><p>Body text</p>
<main><h1>Main heading</h1><p>Main text</p></main>
<article><h2>Article heading</h2><p>Article text</p></article>
</body></html>"""

    segments = normalize_knowledge_content(html, "url")

    assert [segment.text for segment in segments] == [
        "Help",
        "Article heading",
        "Article text",
    ]
    assert [segment.heading_path for segment in segments] == [
        (),
        ("Article heading",),
        ("Article heading",),
    ]


def test_html_main_scope_wins_when_article_has_no_eligible_content() -> None:
    html = b"""<body>
<h1>Body heading</h1><p>Body text</p>
<main><h2>Main heading</h2><p>Main text</p></main>
<article><div>Uncaptured article wrapper text</div></article>
</body>"""

    segments = normalize_knowledge_content(html, "url")

    assert [segment.text for segment in segments] == ["Main heading", "Main text"]
    assert [segment.heading_path for segment in segments] == [
        ("Main heading",),
        ("Main heading",),
    ]


def test_html_empty_and_url_text_safety_fail_closed() -> None:
    with pytest.raises(KnowledgeNormalizationError) as empty:
        normalize_knowledge_content(b"<nav><p>noise only</p></nav>", "url")
    assert empty.value.code == KnowledgeNormalizationErrorCode.EMPTY_CONTENT

    assert normalize_knowledge_content(
        b"\xef\xbb\xbf<article><p>hello</p></article>", "url"
    )[0].text == "hello"

    with pytest.raises(KnowledgeNormalizationError) as invalid_utf8:
        normalize_knowledge_content(b"<p>hello\xff</p>", "url")
    assert invalid_utf8.value.code == KnowledgeNormalizationErrorCode.INVALID_UTF8

    with pytest.raises(KnowledgeNormalizationError) as nul:
        normalize_knowledge_content(b"<p>hello\x00world</p>", "url")
    assert nul.value.code == KnowledgeNormalizationErrorCode.TEXT_INVALID

    tiny = NormalizationLimits(
        max_pdf_bytes=1_000,
        max_text_bytes=4,
        max_pdf_pages=10,
        max_total_chars=100,
        max_segment_chars=100,
        max_segments=10,
    )
    with pytest.raises(KnowledgeNormalizationError) as too_large:
        normalize_knowledge_content(b"<p>x</p>", "url", tiny)
    assert too_large.value.code == KnowledgeNormalizationErrorCode.INPUT_TOO_LARGE


def test_html_normalization_is_deterministic() -> None:
    raw = b"<article><h1>One</h1><p>alpha &amp; beta</p><li>gamma</li></article>"

    first = normalize_knowledge_content(raw, "url")
    second = normalize_knowledge_content(raw, "url")

    assert first == second


def test_html_unexpected_parser_failure_is_safe_and_does_not_log_raw_content(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = "SECRET-HTML-PARSER-FAILURE-c9a2"

    def fail_feed(self: object, data: str) -> None:
        del self, data
        raise RuntimeError(sentinel)

    monkeypatch.setattr(normalization._KnowledgeHtmlParser, "feed", fail_feed)

    with pytest.raises(KnowledgeNormalizationError) as exc_info:
        normalize_knowledge_content(f"<p>{sentinel}</p>".encode(), "url")

    assert exc_info.value.code == KnowledgeNormalizationErrorCode.HTML_MALFORMED
    assert str(exc_info.value) == "Knowledge HTML is malformed or unsupported."
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
