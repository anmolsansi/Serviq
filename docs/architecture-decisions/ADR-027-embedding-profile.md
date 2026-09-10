# ADR-027: V1 embedding profile and deterministic gateway adapter

- **Status:** Accepted
- **Date:** 2026-09-10
- **Ticket:** V1.3.11 / OPE-319 / GitHub #221

## Context

Serviq's knowledge schema already reserves a dimensionless `vector` column, while vector indexing is intentionally blocked until the embedding profile is frozen. V1.3.11 must choose the stable profile before V1.3.12 can safely bind PostgreSQL/pgvector indexing to a dimension.

The ticket also needs a real Serviq gateway boundary that downstream ingestion work can call without requiring production vendor credentials during deterministic CI and contract testing.

## Decision

### Frozen V1 profile

- Internal model alias: `serviq-embedding-v1`.
- Vector dimension: `1536`.
- Maximum request batch: `100` input strings.
- Maximum input length: `32,000` characters per string.
- Request purpose: exactly `embedding`.
- Internal route: `POST /internal/v1/embeddings`.

The dimension is a Serviq-owned contract. Later indexing code may rely on exactly 1536 values per vector. Changing this dimension, alias, batch limit, or input limit requires an ADR/profile change before rollout.

### Gateway and authentication boundary

The route reuses the existing `LLM_GATEWAY_INTERNAL_TOKEN` bearer-token check through `_require_internal_token`. V1.3.11 does not create a public, workforce, customer, or platform-operator embedding endpoint.

`tenantId` and `correlationId` remain required C-4 request context. This ticket does not add a tenant database lookup or a new authorization system inside the gateway. The trusted Serviq caller remains responsible for resolving tenant context before crossing the internal gateway boundary.

### Deterministic fake implementation

`FakeLLMAdapter` is the only embedding implementation in V1.3.11. It performs no network call and requires no provider credential. Each exact input string is expanded deterministically into one 1536-dimensional float vector. Request order is preserved, and repeating the same complete request produces the same vectors and deterministic request ID.

The fake vectors are input-sensitive test fixtures. They are not semantic embeddings and must not be used as evidence of retrieval quality.

The normalized response continues to use the existing C-4 provider field. The fake V1 profile reports the OpenAI provider family with `upstreamModel=serviq-fake-v1`; the fake upstream model is the explicit evidence that no real OpenAI request occurred. Adding a separate fake provider enum is intentionally avoided because that enum is also consumed by real provider-connectivity contracts.

### Fail-closed response contract

Every response vector must contain exactly 1536 floats. The number of returned vectors must exactly equal the number of request inputs. If an adapter returns a different count, the gateway returns a safe `PROVIDER_UNAVAILABLE` failure rather than exposing partial or misaligned results.

Provider-style failures remain bounded Serviq-owned error categories. Raw knowledge input, credentials, tokens, prompts, and provider exception details must not be returned or logged by this path.

## Explicitly out of scope

- Real OpenAI embedding calls.
- Real Anthropic embedding calls.
- Real Gemini embedding calls.
- Real OpenRouter embedding calls.
- Provider credential resolution for embeddings.
- Knowledge chunk persistence or embedding persistence.
- Vector schema migration or index creation.
- Parse/chunk worker orchestration and events.
- Retrieval, ranking, citations, or answer generation.
- Public API or UI behavior.

The existing generation adapters and their shared `LLMAdapter` contract remain unchanged by this ticket.

## Consequences

- V1.3.12 can now bind the vector persistence/index contract to dimension 1536 without guessing.
- Downstream ingestion work has a stable internal C-4 request/response shape and deterministic offline test path.
- Batches larger than 100, inputs longer than 32,000 characters, blank inputs, non-embedding purposes, and wrong-dimensional response vectors fail contract validation.
- A later real-provider embedding implementation must preserve this Serviq-owned profile or introduce an architect-reviewed profile change.

## Rollback

Revert the V1.3.11 code and documentation commits. There is no database migration, vector index, durable embedding data, provider credential, or external-provider state to roll back in this ticket.
