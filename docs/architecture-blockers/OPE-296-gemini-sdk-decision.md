# OPE-296 — Gemini adapter architecture blocker

## Status

**Resolved by ADR-012 and PR #136.**

The original stop was correct: OPE-296 required an architect-approved Gemini SDK before implementation, while ADR-011 explicitly approved only OpenAI and Anthropic. The missing dependency/transport decision has now been made and merged into `main`.

## What OPE-296 is building

OPE-296 adds Gemini as another implementation behind Serviq's provider-neutral Contract C-4. The rest of Serviq can ask the gateway for generation or streaming without importing Gemini SDK types or learning Gemini-specific request and response shapes.

The adapter translates Serviq messages and bounded request options into the approved Gemini client, normalizes provider responses back into C-4, maps provider failures into Serviq's five error categories, and prevents API keys, raw provider exceptions, and provider-specific objects from escaping the adapter boundary.

## Original blocking fact

Before ADR-012, `docs/architecture-decisions/ADR-011-provider-sdk-baseline.md` froze only:

- `openai==2.53.0`
- `anthropic==0.121.0`

ADR-011 explicitly excluded Gemini. OPE-296 therefore reached its `Needs Architect Decision` stop condition and correctly did not guess a dependency inside feature code.

## Decision that resolved the blocker

`docs/architecture-decisions/ADR-012-gemini-sdk-baseline.md`, merged through PR #136, freezes the following rules:

1. official Google package `google-genai==2.17.0`;
2. Gemini Developer API with server-resolved tenant BYOK credentials;
3. Python 3.14 compatibility as a prerequisite;
4. explicit Developer API mode rather than caller/environment-selected enterprise routing;
5. Serviq-owned timeout and retry policy, with one upstream attempt and no hidden SDK retries;
6. leading C-4 system messages mapped to Gemini `system_instruction`;
7. C-4 user messages mapped to `user` and assistant messages mapped internally to Gemini's `model` role;
8. native JSON Schema structured output where C-4 requests a response schema;
9. asynchronous generation/streaming behind the existing C-4 boundary;
10. safe normalization into the five existing C-4 error categories;
11. mock/fake-only required CI tests;
12. no Gemini-specific extension to C-4.

## Why this matters

The architecture decision makes the implementation reproducible and reviewable. The feature code is no longer making an implicit package or transport choice. A future engineer can tell exactly why this SDK is installed, which API mode it is permitted to use, who owns retry/timeout policy, and which behaviors must remain provider-neutral.

## Current implementation status

The architecture blocker is closed. Runtime implementation is being completed in branch `agent/ope-296-gemini-adapter-implementation` and PR #137.

The ticket must remain open until the following are true:

- Gemini non-stream generation passes C-4 tests;
- Gemini streaming passes C-4 tests;
- system/user/assistant translation is verified;
- structured output is verified;
- auth, rate-limit, timeout, unavailable, and invalid-request mappings are verified;
- secret/raw-provider leakage checks pass;
- provider SDK types remain contained;
- premium security review is recorded;
- repository CI and Security workflows pass;
- implementation PR is merged.

## Product impact

Resolving the blocker lets Serviq add Gemini without weakening the provider-neutral design. Product and agent code still talk only to Serviq's own C-4 objects. Gemini becomes replaceable implementation detail rather than a dependency that leaks into the rest of the platform.
