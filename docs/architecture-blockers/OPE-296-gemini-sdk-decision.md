# OPE-296 — Gemini adapter architecture blocker

## Status

**Needs Architect Decision.** No Gemini adapter code was added because the ticket's explicit stop condition is currently true.

## What OPE-296 is trying to build

OPE-296 is meant to add Gemini as another implementation behind Serviq's provider-neutral Contract C-4. Once implemented, the rest of Serviq should be able to ask the gateway for generation or streaming without importing Gemini SDK types or learning Gemini-specific request and response shapes.

The adapter must translate Serviq messages and budgets into the approved Gemini client, normalize the response back into C-4, translate provider failures into Serviq error codes, and prevent API keys, raw provider exceptions, or provider-specific objects from escaping the adapter boundary.

## What was inspected before coding

The builder inspected:

- Linear OPE-296 and its stop conditions;
- `docs/repo_context.md`;
- `docs/TECH_STACK.md`;
- `docs/ARCHITECTURE.md` Contract C-4;
- `docs/architecture-decisions/ADR-011-provider-sdk-baseline.md`;
- `services/llm-gateway/pyproject.toml`;
- the existing `services/llm-gateway/app/adapters/base.py` interface;
- the implemented OpenAI adapter pattern.

## Blocking fact

ADR-011 freezes only these official provider SDKs for the current gateway:

- `openai==2.53.0`
- `anthropic==0.121.0`

ADR-011 also explicitly states that its scope does **not** approve Gemini dependencies. The current LLM Gateway manifest therefore contains no approved Gemini SDK dependency.

OPE-296 says to stop with `Needs Architect Decision` when no approved Gemini SDK exists in repository context. That condition is satisfied exactly.

## Why no dependency was added from this ticket

A feature-builder ticket is not allowed to silently decide which third-party package becomes part of Serviq's production dependency surface. Choosing `google-genai`, another Google package, a raw HTTP implementation, or a compatibility layer would affect:

- dependency provenance and security review;
- Python 3.14 compatibility;
- request/streaming behavior;
- timeout and retry semantics;
- exception types and error normalization;
- lockfile/reproducibility policy;
- future upgrade and maintenance responsibility.

Making that decision inside OPE-296 would bypass the repository's contract-change discipline and would directly violate the ticket's stop condition.

## Decision required to unblock OPE-296

An architect-approved change must freeze:

1. the official Gemini SDK/package or explicitly approved alternative transport;
2. the exact compatible version or version policy;
3. Python 3.14 support expectations;
4. timeout/retry ownership consistent with C-4;
5. dependency locking/reproducibility expectations for the LLM Gateway;
6. any known unsupported C-4 capabilities that the adapter must reject explicitly.

After that decision is merged, OPE-296 can implement only the provider adapter, mocked SDK tests, and required security review without changing C-4.

## Product impact

Stopping here protects Serviq from an accidental provider-specific architecture decision. It keeps the provider-neutral gateway real rather than nominal and ensures that a future Gemini implementation is reproducible, reviewable, and replaceable instead of depending on an arbitrary package choice made during feature coding.

## What changed in this branch

Only this architecture-blocker record was added. No production code, dependency, C-4 schema, provider routing, model alias, secret handling, or agent runtime behavior was changed.
