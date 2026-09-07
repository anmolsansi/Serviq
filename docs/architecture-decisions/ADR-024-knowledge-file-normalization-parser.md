# ADR-024 — Knowledge file normalization parser

- Status: Accepted
- Date: 2026-09-07
- Linear: OPE-315
- GitHub: #208

## Context

ADR-023 and CCR-008 finish V1.3.07 by creating a versioned `knowledge_document` and staging `serviq.knowledge.parse.v1` with a tenant-scoped raw-object locator. The compact roadmap assigns PDF/Markdown/text normalization to V1.3.08, HTML/help-center normalization to V1.3.09, and deterministic heading-aware chunking to V1.3.10.

The remaining V1.3.08 decision is deliberately narrower than a parse-event worker. The repository does not yet freeze where normalized segments are durably stored or what downstream event hands them to V1.3.10. Activating a Kafka consumer here would force V1.3.08 to invent persistence, retry, lifecycle, and chunk-handoff contracts owned by later work.

## Decision

### Boundary

V1.3.08 adds a pure normalization library inside the worker service. It accepts raw bytes plus one of the file source types `pdf`, `markdown`, or `text` and returns immutable, deterministic plain-text segments.

It does **not**:

- consume `serviq.knowledge.parse.v1`;
- read object storage;
- write PostgreSQL;
- mutate `knowledge_sources` or `knowledge_documents`;
- publish a new event;
- implement HTML parsing, chunking, embedding, indexing, or retrieval.

A later ticket may call this library from the durable parse worker after the missing orchestration and persistence contracts are frozen.

### Public library contract

```python
normalize_knowledge_content(
    raw_bytes: bytes,
    source_type: str,
    limits: NormalizationLimits = DEFAULT_NORMALIZATION_LIMITS,
) -> tuple[NormalizedSegment, ...]
```

Each `NormalizedSegment` contains:

- `ordinal`: zero-based deterministic order;
- `text`: non-empty normalized plain text;
- `page_number`: one-based PDF page number, otherwise `None`;
- `heading_path`: Markdown heading ancestry, otherwise empty;
- `start_line` / `end_line`: one-based source line provenance for Markdown/text, otherwise `None`.

Segment data never contains tenant IDs, object keys, raw bytes, file names, URLs, credentials, or other operational context.

### Fixed limits

The existing upload boundary already caps PDF bytes at 25 MiB and Markdown/text bytes at 5 MiB. The parser revalidates these limits because raw bytes remain untrusted at the worker boundary.

V1.3.08 additionally freezes:

- PDF pages: at most `2_000`;
- normalized output: at most `5_242_880` characters per document;
- one segment: at most `32_768` characters;
- segment count: at most `20_000`.

The PDF library's own decompression and malformed-input resource limits remain enabled. V1.3.08 does not increase or disable them.

### Text and Markdown

Markdown/text decode with `utf-8-sig` and strict error handling. NUL bytes are rejected.

Both formats normalize CRLF/CR to LF and remove trailing horizontal whitespace. Empty blocks are omitted. Long logical blocks are split deterministically without exceeding the segment bound.

Text uses blank-line-separated blocks and records their one-based source line range.

Markdown additionally:

- recognizes ATX headings levels 1–6;
- emits heading text without `#` markers and updates deterministic heading ancestry;
- removes list and blockquote markers while retaining their text;
- removes fenced-code delimiters while retaining fenced content as inert text;
- reduces common emphasis, inline-code, image, link, and HTML-tag syntax to readable inert text;
- never evaluates HTML, code, links, or embedded instructions.

### PDF

Use `pypdf>=6.17,<6.18` without crypto extras. `pypdf 6.17.0` is the accepted V1 implementation dependency.

The parser constructs `PdfReader(BytesIO(raw_bytes), strict=True)`. Strict mode turns correctable structural problems into failures instead of silently accepting malformed input.

Security behavior is fixed:

- reject encrypted PDFs after reader construction and before page extraction;
- never call `decrypt`;
- extract text only through page text extraction;
- never run JavaScript/actions, follow links, extract attachments, launch external programs, or perform OCR/image extraction;
- skip blank pages;
- if all pages are blank/image-only, return a safe empty-content failure rather than introducing OCR.

Any PDF parse/extraction failure is converted to a stable parser error without returning or logging the upstream exception text.

### Safe errors

`KnowledgeNormalizationError` exposes one stable code and a generic message. Allowed codes are:

- `KNOWLEDGE_NORMALIZATION_SOURCE_TYPE_UNSUPPORTED`;
- `KNOWLEDGE_NORMALIZATION_INPUT_TOO_LARGE`;
- `KNOWLEDGE_NORMALIZATION_INVALID_UTF8`;
- `KNOWLEDGE_NORMALIZATION_TEXT_INVALID`;
- `KNOWLEDGE_NORMALIZATION_PDF_MALFORMED`;
- `KNOWLEDGE_NORMALIZATION_PDF_ENCRYPTED`;
- `KNOWLEDGE_NORMALIZATION_PDF_PAGE_LIMIT_EXCEEDED`;
- `KNOWLEDGE_NORMALIZATION_OUTPUT_TOO_LARGE`;
- `KNOWLEDGE_NORMALIZATION_SEGMENT_LIMIT_EXCEEDED`;
- `KNOWLEDGE_NORMALIZATION_EMPTY_CONTENT`.

Parser code does not log source text. Callers may log bounded identifiers plus the safe error code, never raw document content.

## Alternatives considered

### Activate the parse-event consumer now

Rejected. The repository freezes the input event but not the normalized-output persistence or V1.3.10 handoff contract. Implementing a consumer would silently make architecture decisions outside V1.3.08.

### Store normalized blocks directly in `knowledge_chunks`

Rejected. V1.3.10 owns deterministic chunking, token counts, overlap, and final chunk provenance. Writing parser segments into `knowledge_chunks` would conflate two roadmap stages and make later migration/rollback harder.

### Add OCR or a native PDF tool

Rejected for V1. The ticket explicitly excludes OCR. A native subprocess also expands deployment and untrusted-file execution risk without being required for text-based PDFs.

### Implement a custom PDF parser

Rejected. PDF syntax, filters, encryption, malformed-input recovery, and resource bounds are security-sensitive. The accepted maintained pure-Python dependency is smaller and safer than maintaining a bespoke parser.

## Validation

Required evidence is worker-local because this ticket adds no API, database, broker, or object-storage boundary:

- focused normalization unit tests for text, Markdown, and PDF;
- malformed/encrypted/blank PDF tests;
- input/output/page/segment bound tests;
- deterministic-repeat test;
- raw-content error/log privacy test;
- worker Ruff, strict mypy, full pytest, and frozen-lock validation;
- repository CI and Security checks.

## Rollback

Revert the parser, tests, dependency/lock, and documentation changes. No schema, API, Kafka, object-storage, or durable-state rollback is required because no runtime consumer is activated by V1.3.08.