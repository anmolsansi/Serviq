# ADR-025: Knowledge HTML/help-center normalization parser

- Status: Accepted
- Date: 2026-09-07
- Ticket: V1.3.09 / OPE-316 / GitHub #211

## Context

ADR-023 and CCR-008 stage `serviq.knowledge.parse.v1` after a versioned knowledge document is created. ADR-024 then adds the pure worker-side normalization library for `pdf`, `markdown`, and `text` while deliberately leaving parse-event consumption, normalized-output persistence, lifecycle mutation, and V1.3.10 chunking out of scope.

The remaining V1.3.09 roadmap requirement is bounded: normalize HTML/help-center content by extracting title, headings, article paragraphs, and lists while removing script, style, form, navigation, and similar noise. V1 must not add a headless browser or anti-bot bypass.

The repository's durable knowledge-source contract already represents web pages as `source_type = "url"`. V1.3.07 also places `sourceType: "url"` in the existing parse handoff. Introducing a second durable source type such as `html` would silently change API, database, event, and migration contracts that this ticket does not own.

## Decision

V1.3.09 extends `services/worker/app/core/knowledge_normalization.py` as a pure in-process library. `normalize_knowledge_content(...)` accepts `source_type="url"` for HTML/help-center bytes and returns the existing immutable `NormalizedSegment` contract.

The parser uses Python's standard-library `html.parser.HTMLParser` with `convert_charrefs=True`. No new dependency is added.

The parser receives already-fetched bytes only. It does not:

- fetch or follow URLs;
- crawl pages;
- execute JavaScript;
- render a DOM in a browser;
- inspect browser state;
- solve CAPTCHAs or anti-bot challenges;
- launch external processes;
- read object storage;
- persist normalized content;
- consume Kafka events.

Those boundaries keep V1.3.09 deterministic, testable, reversible, and aligned with the V1 roadmap.

## Input and output contract

The public function remains:

```python
normalize_knowledge_content(
    raw_bytes: bytes,
    source_type: str,
    limits: NormalizationLimits = DEFAULT_NORMALIZATION_LIMITS,
) -> tuple[NormalizedSegment, ...]
```

Supported source types become:

- `pdf`
- `markdown`
- `text`
- `url`

`url` bytes use the same strict UTF-8-SIG decoder and NUL rejection as text and Markdown. URL input uses the existing `max_text_bytes` limit of 5 MiB. Existing total-output, per-segment, and segment-count limits remain unchanged.

HTML output reuses `NormalizedSegment` without new fields. HTML segments have `page_number=None`, `start_line=None`, and `end_line=None`. Heading ancestry is populated for headings and content blocks.

## Extraction rules

The parser recognizes only bounded visible-content structures:

- `<title>`: emit the first non-empty document title as the first segment.
- `<h1>` through `<h6>`: emit heading text and update heading ancestry.
- `<p>`: emit visible paragraph text.
- `<li>`: emit visible list-item text.
- `<br>`: preserve an explicit line break inside a captured block.

All other tags are structural or inline wrappers. Their attributes are never copied into normalized output. Unknown inline tags can contribute visible character data only while inside one of the recognized captures.

Text whitespace is normalized deterministically. Source indentation/newlines collapse like ordinary HTML whitespace. Only explicit `<br>` produces an internal normalized line break.

## Content-scope precedence

Help-center pages frequently contain repeated site chrome outside the article. V1.3.09 therefore selects one content scope after parsing:

1. If at least one eligible candidate appears inside `<article>`, use article candidates.
2. Otherwise, if at least one eligible candidate appears inside `<main>`, use main candidates.
3. Otherwise, use eligible body/global candidates.

The document title remains first when present regardless of the selected content scope.

Heading ancestry is computed after scope selection. This prevents headings from discarded navigation/body chrome from contaminating article heading paths.

## Noise and executable-subtree removal

The following subtrees are ignored completely, including their descendants and text:

- `script`
- `style`
- `form`
- `nav`
- `noscript`
- `template`
- `svg`
- `canvas`
- `iframe`
- `object`
- `embed`
- `header`
- `footer`
- `aside`

HTML comments, declarations, attributes, links, image attributes, and form-control values are not emitted.

This denylist is intentionally structural. It is not a security sanitizer for re-rendering HTML because normalized output is plain text only.

## Failure behavior

The existing safe failures still apply to URL bytes:

- `KNOWLEDGE_NORMALIZATION_INPUT_TOO_LARGE`
- `KNOWLEDGE_NORMALIZATION_INVALID_UTF8`
- `KNOWLEDGE_NORMALIZATION_TEXT_INVALID`
- `KNOWLEDGE_NORMALIZATION_OUTPUT_TOO_LARGE`
- `KNOWLEDGE_NORMALIZATION_SEGMENT_LIMIT_EXCEEDED`
- `KNOWLEDGE_NORMALIZATION_EMPTY_CONTENT`

V1.3.09 adds:

- `KNOWLEDGE_NORMALIZATION_HTML_MALFORMED`

Unexpected parser failures map to that stable code and a generic message. Raw HTML and upstream exception text are never returned or logged by this parser.

A page containing no non-empty title, heading, paragraph, or list-item text fails with `KNOWLEDGE_NORMALIZATION_EMPTY_CONTENT`.

## Security and privacy

The parser treats HTML as untrusted inert input.

- No embedded script or active content executes.
- No browser or network boundary exists in the parser.
- HTML attributes and URLs do not enter normalized output.
- Raw knowledge text is not logged by parser code.
- Existing bounded input/output limits remain enabled.
- No tenant/auth contract changes occur because the library has no tenant or persistence boundary.

## Alternatives considered

### Add Beautiful Soup, lxml, or another HTML dependency

Rejected for V1. The required extraction surface is small enough for the standard library. A new parser dependency would add lockfile, supply-chain, upgrade, and audit cost without a current requirement that justifies it.

### Add a headless browser

Rejected. It contradicts the V1 acceptance criterion, materially increases resource and security risk, and would combine fetching/rendering/anti-bot behavior with normalization.

### Add a new `html` knowledge source type

Rejected. The current durable contract already uses `url`. A new source type would require API, database, event, migration, and compatibility work outside V1.3.09.

### Parse every visible text node

Rejected. It would collect navigation, controls, banners, and unrelated chrome, reducing retrieval quality and making output less deterministic across site templates.

## Operational impact

No deployment topology, database, environment variable, event, network policy, or dependency changes are required.

Rollback is a normal code/docs revert. There is no migration or durable-data reconciliation step.

## Validation

V1.3.09 must cover:

- normal article extraction;
- title and heading ancestry;
- list extraction;
- script/style/form removal;
- noisy navigation/header/footer/aside removal;
- article-over-main/body precedence;
- main-over-body precedence;
- empty-content failure;
- strict UTF-8/NUL/input-size behavior for URL bytes;
- deterministic repeated output;
- raw-sensitive-content non-leakage in errors/logs;
- continued rejection of unsupported `sitemap` normalization.

Focused worker tests, Ruff, strict mypy, full worker tests, repository CI, Security, and the existing integration workflows must pass before merge.
