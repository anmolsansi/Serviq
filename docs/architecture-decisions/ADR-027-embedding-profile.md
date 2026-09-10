# ADR-027: Embedding Profile and Gateway Adapter

**Date:** 2026-09-10
**Status:** Accepted
**Ticket:** V1.3.11

## Context

Serviq requires an embedding infrastructure to support its grounded retrieval system (MAS-4). Before building the actual parsing/indexing worker or retrieving documents, we must define the exact contract between the control plane/worker and the LLM Gateway for generating embeddings.

We need to freeze the dimensionality and the batch sizing constraints. If we do not freeze a batch policy, large document ingestion might attempt to embed thousands of chunks at once, leading to gateway timeouts, out-of-memory errors, or provider rate limits. If we do not freeze dimensions, vector search indexing and schema configurations cannot be safely finalized.

## Decision

1. **Embedding Profile Alias:** `serviq-embedding-v1`. This is the internal alias used by Serviq.
2. **Dimension Size:** `1536`. This aligns with the industry standard for production-grade fast embedding models (like `text-embedding-3-small` and `text-embedding-ada-002`) and provides an optimal balance for `pgvector` indexing in PostgreSQL.
3. **Batch Policy:** Maximum `100` inputs per batch request to the gateway.
4. **Input Size Policy:** Maximum `32,000` characters per input string.
5. **Gateway Protocol:** We will introduce a dedicated `GatewayEmbeddingRequest` and `GatewayEmbeddingResponse` in the C-4 contract, rather than overloading the existing generation/chat contract.

## Consequences

- The worker and API must batch their embedding requests to chunks of 100 or fewer.
- Database migrations and pgvector indexes (when implemented) will be hardcoded to `1536` dimensions.
- The LLM Gateway will enforce the `100` batch size limit at the schema level using Pydantic, returning a `422 Validation Error` if the limit is exceeded.
- Providers (e.g., OpenAI, Anthropic, Gemini, OpenRouter) will each need a specific embedding adapter implementation. For this initial ADR, only the deterministic `FakeLLMAdapter` will implement embeddings to unblock downstream integration and testing.
