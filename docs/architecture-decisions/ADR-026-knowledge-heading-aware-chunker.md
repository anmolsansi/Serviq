# ADR-026: Deterministic heading-aware knowledge chunker

- Status: Accepted
- Date: 2026-09-09
- Ticket: V1.3.10 / OPE-317 / GitHub #214

## Context

ADR-024 and ADR-025 implement pure worker-side normalization for file and HTML/help-center knowledge. Their output is an ordered tuple of immutable `NormalizedSegment` values carrying text, zero-based ordinal, heading ancestry, and coarse page/line provenance. Both decisions deliberately leave final chunking, token counts, overlap, and chunk provenance to V1.3.10.

The repository already has a durable `knowledge_chunks` schema, but parse-event consumption and normalized-output persistence are not active. V1.3.10 therefore needs a deterministic transformation library, not a database writer, Kafka consumer, embedding pipeline, or retrieval service.

No embedding profile or provider tokenizer has been frozen yet. Coupling chunk construction to an OpenAI, Anthropic, Google, or other model tokenizer now would introduce a dependency and make replay behavior vary with a downstream model decision that this ticket does not own.

## Decision

V1.3.10 adds `services/worker/app/core/knowledge_chunking.py` as a pure in-process library. It consumes already-normalized `NormalizedSegment` values and returns immutable `KnowledgeChunk` values. It performs no I/O and has no tenant, authentication, storage, database, event, network, or provider boundary.

The public function is:

```python
chunk_normalized_segments(
    segments: Sequence[NormalizedSegment],
    policy: ChunkPolicy = DEFAULT_CHUNK_POLICY,
) -> tuple[KnowledgeChunk, ...]
```

## Frozen V1 token policy

For V1, one token is one non-whitespace run matched by Python Unicode regex `\S+`.

This is intentionally a repository-owned deterministic counting unit, not a claim that it matches any model provider's billing or context-window tokenizer. The policy exists so identical normalized input always produces identical boundaries and token counts without adding a tokenizer dependency before the embedding profile is selected.

Changing this token definition requires retrieval-quality evaluation and an ADR update before rollout.

## Frozen V1 size and overlap policy

`ChunkPolicy` defaults are:

- `max_tokens = 512`;
- `overlap_tokens = 64`;
- `max_chunks = 20_000`.

The policy rejects booleans and non-integer values. `max_tokens` and `max_chunks` must be positive. `overlap_tokens` must be non-negative and strictly smaller than `max_tokens`.

A heading group containing at most 512 tokens produces exactly one chunk. Larger groups use deterministic token-boundary windows with a stride of `512 - 64 = 448` tokens. Consecutive non-final windows therefore overlap by exactly 64 tokens.

Boundary ties are source-order deterministic. Exactly 512 tokens remain one chunk. With 513 tokens, the first chunk covers tokens 0–511 and the second starts at zero-based token index 448.

## Input contract

Input order is contractual. `NormalizedSegment.ordinal` values must be exactly contiguous `0..n-1` in supplied order. The chunker does not sort, renumber, deduplicate, or repair malformed normalized input.

Empty input fails safely. Every accepted segment must contain at least one V1 token. Token-empty segments fail rather than disappearing silently.

## Heading grouping

Heading ancestry is used as a deterministic semantic boundary.

1. Leading document-preamble segments with `heading_path == ()` attach to the first following segment with a non-empty heading path. This keeps an HTML document title with its first article section.
2. If no non-empty heading path exists, all supplied segments form one empty-path group.
3. After the leading preamble, groups are consecutive runs whose `heading_path` values are exactly equal.
4. A later empty heading path is treated like any other changed heading path. The chunker never searches ahead, reorders groups, or merges non-consecutive sections.

Within one group, segment text is joined with exactly two newline characters. Chunk windows are then selected from that group text.

## Text preservation

Chunk boundaries begin at the first character of the first selected V1 token and end after the last character of the last selected V1 token. Characters and whitespace between those token boundaries are preserved exactly from the normalized group text.

The chunker does not summarize, stem, rewrite, infer sentences, duplicate headings synthetically, call an LLM, or normalize text again.

## Output contract

`KnowledgeChunk` contains:

- `ordinal: int`;
- `text: str`;
- `token_count: int`;
- `heading_path: tuple[str, ...]`;
- `provenance: tuple[ChunkProvenance, ...]`.

`ChunkProvenance` contains:

- `segment_ordinal: int`;
- `page_number: int | None`;
- `heading_path: tuple[str, ...]`;
- `start_line: int | None`;
- `end_line: int | None`.

Chunk ordinals are zero-based and contiguous. `token_count` is the exact number of V1 tokens in the selected window. A chunk's `heading_path` is the heading path of its group.

Provenance includes each normalized segment whose character span intersects the selected chunk window, once and in source order. When a window uses only part of a normalized segment, the chunker preserves that segment's existing coarse page/line metadata. It does not fabricate finer offsets that the normalization layer did not supply.

## Failure behavior

Failures use stable codes and generic messages only:

- `KNOWLEDGE_CHUNKING_EMPTY_INPUT`;
- `KNOWLEDGE_CHUNKING_INVALID_SEGMENTS`;
- `KNOWLEDGE_CHUNKING_TOKEN_EMPTY_SEGMENT`;
- `KNOWLEDGE_CHUNKING_INVALID_POLICY`;
- `KNOWLEDGE_CHUNKING_CHUNK_LIMIT_EXCEEDED`.

Raw knowledge text is never included in chunking errors or logs. The library itself emits no logs.

## Alternatives considered

### Use the eventual embedding-model tokenizer now

Rejected. No embedding profile or tokenizer contract is frozen. Adding one now would couple this ticket to a future provider/model decision, add dependency and lockfile cost, and make deterministic replay depend on provider-specific behavior.

### Chunk by character count

Rejected. The roadmap explicitly requires `token_count` and overlap. Character windows behave poorly across languages and long/short lexical units and would leave token semantics undefined.

### Greedily combine content across heading changes

Rejected. That weakens the heading-aware requirement and can mix unrelated sections. V1 uses exact heading-path runs as explicit semantic boundaries.

### Remove overlap

Rejected. The frozen V1 contract requires overlap. A fixed 64-token overlap is simple, deterministic, and bounded.

### Persist chunks in this ticket

Rejected. Parse-consumer activation, durable chunk replacement semantics, retries, lifecycle transitions, and database consistency are separate roadmap concerns. Keeping V1.3.10 pure makes this policy independently testable and reversible.

## Security and privacy

The chunker operates only on in-memory normalized text supplied by its caller. It does not read URLs, files, object storage, credentials, tenant context, or databases. It does not call providers or execute content. Errors are bounded and generic, and raw text is not logged.

Upstream normalization already bounds total output. V1 also caps generated chunks at 20,000, preventing an invalid custom policy or adversarially fragmented input from producing unbounded result cardinality.

## Operational impact and rollback

There is no deployment-topology, environment-variable, dependency, database, event, or migration change.

Rollback is a normal code/docs revert. No durable data reconciliation is required because this ticket does not persist chunk output.

## Validation

V1.3.10 must cover:

- short single-chunk input;
- long bounded windows with exact overlap;
- heading changes and leading title/preamble behavior;
- list-segment ordering;
- exact 512/513-token ties;
- repeated-input determinism;
- page/line provenance preservation;
- empty input;
- malformed/non-contiguous segment order;
- token-empty input and privacy-safe errors;
- invalid policy values;
- deterministic `max_chunks` enforcement.

Focused worker pytest, Ruff, strict mypy, full worker validation, repository CI, and Security must pass before merge.

## Change control

The token definition, maximum size, overlap, heading-group rules, separator behavior, or provenance semantics are retrieval policy. Any change to them requires evaluation evidence and an ADR update before deployment. A builder must not tune these values opportunistically while implementing later embedding or retrieval tickets.
