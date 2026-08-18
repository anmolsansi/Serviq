# OPE-297 — OpenRouter adapter architecture blocker

## Status

**Resolved by ADR-013 and GitHub PR #141.**

This document originally recorded a legitimate `Needs Architect Decision` stop condition. The history is preserved because it explains why OPE-297 did not immediately add runtime code and what had to be decided first.

## What OPE-297 is trying to build

OPE-297 makes OpenRouter interchangeable with the other providers behind Serviq Contract C-4. The adapter accepts only a server-resolved BYOK credential and validated upstream model, uses a Serviq-controlled endpoint, normalizes generation and streaming results, and prevents caller-controlled base URLs or provider-only response details from escaping into shared contracts.

## Original blocking fact

At the first implementation attempt, the repository had no frozen OpenRouter transport/client choice.

ADR-011 approved only the official OpenAI and Anthropic SDK dependencies and explicitly did not approve an OpenRouter dependency or transport. Although OpenRouter exposes an OpenAI-compatible API, choosing to reuse the OpenAI SDK would still have answered architecture questions about endpoint ownership, retries, headers, error behavior, and upgrade coupling.

OPE-297 explicitly required the builder to stop in that state, so the original branch added this blocker record instead of inventing a transport decision inside feature code.

## How the blocker was resolved

ADR-013 — `docs/architecture-decisions/ADR-013-openrouter-transport-baseline.md` — was created on a dedicated architecture branch and merged through PR #141 after CI #184 and Security #160 passed.

The architecture merge commit is:

`592136fd02a22976ec87a685436810a89bc9b4fa`

ADR-013 freezes:

1. the existing pinned `openai==2.53.0` Python SDK as the OpenRouter transport;
2. OpenAI-compatible Chat Completions as the OPE-297 protocol surface;
3. `https://openrouter.ai/api/v1` as the immutable Serviq-owned base URL;
4. no caller-, model-, tenant-, or agent-controlled endpoint override;
5. server-resolved OpenRouter BYOK credentials only;
6. validated `AdapterContext.upstream_model` only;
7. C-4 timeout and output-token budgets;
8. `max_retries=0`, leaving retries/fallback to Serviq orchestration above the adapter;
9. JSON Schema structured-output behavior;
10. ordered streaming behavior;
11. safe five-category C-4 error normalization;
12. no OpenRouter routing controls, plugins, fallback arrays, or arbitrary provider headers in this ticket;
13. mock/fake-only required CI tests.

## Why the chosen transport is appropriate

OpenRouter's official documentation explicitly supports pointing the OpenAI SDK at its OpenAI-compatible API base URL. Serviq already pins and reviews that SDK for the OpenAI adapter, so this approach avoids introducing another runtime library solely for an API surface the existing SDK already supports.

The important distinction is that Serviq does **not** reuse the `OpenAIAdapter` class. OPE-297 has its own `OpenRouterAdapter`, its own provider identity, OpenRouter-specific in-band error handling, and its own tests/security review.

## Security boundary that is now frozen

Tenants can select a saved OpenRouter provider connection and a validated model configuration. They cannot select an outbound URL.

The base URL is a code-owned constant in the OpenRouter adapter. C-4 has no `baseUrl` or `endpoint` field, and the adapter does not read a destination from tenant metadata, model configuration, agent configuration, or arbitrary environment variables.

This prevents the provider adapter from becoming an arbitrary outbound proxy or SSRF-like primitive.

## Runtime follow-up

After ADR-013 merged, runtime work began on a fresh branch created from the architecture-approved `main` branch:

`agent/ope-297-openrouter-adapter-implementation`

Runtime PR:

`#142 — feat: implement OpenRouter C-4 adapter for OPE-297`

The runtime branch implements and tests the now-frozen contract without changing C-4.

## Why this audit trail remains useful

Deleting the old blocker text after resolving it would hide an important engineering decision. Keeping the before-and-after history shows that the feature builder did not guess around an architecture gate and that the transport became authorized only after a separate reviewed decision.
