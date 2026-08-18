# ADR-012 — Official Gemini SDK baseline for OPE-296

## Status

Accepted.

## Context

OPE-296 requires a Gemini generation and streaming adapter behind Serviq's provider-neutral Contract C-4. The ticket explicitly says implementation must stop if the Gemini transport and SDK are not already approved.

That stop condition was reached correctly. ADR-011 approves only the OpenAI and Anthropic SDKs and explicitly excludes Gemini. The LLM Gateway dependency manifest therefore had no architecture-approved Gemini dependency to use.

This ADR resolves that prerequisite without changing Contract C-4, model routing, model aliases, provider secrets, the agent runtime, or any shared provider-neutral schema.

The gateway runtime is Python 3.14. The approved dependency must therefore support Python 3.14, expose asynchronous non-stream and streaming generation, allow request timeout control, remain isolated inside the provider adapter boundary, and be pinned tightly enough that CI does not silently change adapter behavior.

## Decision

Serviq approves Google's official Gen AI Python SDK for the Gemini adapter:

- Package: `google-genai`
- Version: `google-genai==2.17.0`
- Provider API mode: Gemini Developer API using a server-resolved tenant BYOK API key
- Python runtime: the package metadata for 2.17.0 explicitly lists Python 3.14 support

Version 2.17.0 was released by the official `googleapis/python-genai` repository on 2026-08-06 and was the latest published release when this decision was made.

The dependency must be exact-pinned in `services/llm-gateway/pyproject.toml`. A future SDK upgrade requires an intentional dependency review rather than changing the adapter transitively or silently.

## Client construction and transport ownership

The Gemini adapter will construct the official SDK client with the resolved API key passed through `AdapterContext`. The adapter must not read a Gemini API key from request JSON, query parameters, arbitrary environment variables, or relational provider metadata.

Serviq owns the request timeout and any future retry/fallback policy. Provider-SDK retry behavior must not create hidden duplicate requests underneath Serviq. The adapter therefore configures the SDK so one provider call means one upstream attempt (`HttpRetryOptions(attempts=1)`) and applies the already validated C-4 timeout budget through SDK HTTP options.

OPE-296 does not authorize caller-controlled base URLs, Vertex AI project/location selection, custom provider endpoints, or enterprise routing. Those would require separate architecture decisions.

## C-4 message translation

Gemini's provider-specific message representation remains internal to the adapter.

The translation rules are:

1. Leading C-4 `system` messages are joined in order with a blank line and sent as Gemini's `system_instruction`.
2. C-4 `user` messages map to Gemini content with role `user`.
3. C-4 `assistant` messages map to Gemini content with role `model` because Gemini uses `model` for assistant-authored conversation history.
4. A C-4 system message that appears after conversational messages is rejected as `PROVIDER_INVALID_REQUEST` rather than being reordered silently.
5. At least one non-system conversational message is required.
6. Message content is passed through without hidden prompt injection, rewriting, or provider-specific control strings.

These rules preserve C-4 meaning while making provider limitations explicit.

## Structured output

Contract C-4 already supports an optional `responseSchema` object. When it is present, the adapter may use the official Gemini structured-output fields:

- `response_mime_type="application/json"`
- `response_json_schema=<the validated C-4 JSON Schema object>`

The returned JSON text must be parsed into the Serviq-owned `structured` object before it crosses the adapter boundary. For streaming structured output, provider text chunks may be buffered and parsed only after the stream completes, then emitted as a provider-neutral `structuredDelta`.

If the SDK, selected model, or provider rejects the requested schema/capability, the adapter returns the normalized `PROVIDER_INVALID_REQUEST` category. It must never drop `responseSchema` and silently fall back to unstructured text.

## Streaming behavior

The implementation will use the official asynchronous Gemini SDK streaming API and preserve provider chunk order. Raw Gemini chunk types must never leave `app.adapters.gemini`.

For text streaming, each available text delta is emitted as a C-4 `GatewayStreamEvent.contentDelta` without trimming or rewriting whitespace.

For structured streaming, partial JSON text is buffered until it can be validated as the requested structured result. The adapter then emits a Serviq-owned `structuredDelta` and terminal metadata.

A stream that ends without sufficient terminal/provider output metadata is treated as `PROVIDER_UNAVAILABLE` rather than being presented as a successful incomplete result.

## Response metadata

The adapter will normalize only metadata already frozen by C-4:

- `provider` is `gemini`;
- `upstreamModel` is the already resolved `AdapterContext.upstream_model`;
- input/output token counts are taken from Gemini usage metadata when supplied;
- finish reason is normalized from the Gemini candidate finish reason;
- `requestId` is populated only if the official SDK exposes a stable public request identifier for the response. Otherwise it remains `null`, which C-4 already permits.

No raw Gemini response, headers, safety metadata, SDK model object, or Gemini-only field is added to C-4 by this ADR.

## Error normalization

Gemini failures must be collapsed into the five existing C-4 categories with Serviq-authored messages only:

- 401/403 or equivalent authentication/permission failure -> `PROVIDER_AUTH_FAILED`;
- HTTP 429 -> `PROVIDER_RATE_LIMITED`;
- SDK/transport timeout -> `PROVIDER_TIMEOUT`;
- transport failure, provider 5xx, or equivalent service outage -> `PROVIDER_UNAVAILABLE`;
- invalid model/request/schema/capability and other applicable provider 4xx failures -> `PROVIDER_INVALID_REQUEST`.

Raw provider response bodies, SDK exception text, response headers, stack objects, and API keys must not cross the adapter boundary or be stored in normalized errors.

## Adapter boundary rules

1. Gemini SDK imports and types are restricted to `app.adapters.gemini` and its tests.
2. Public gateway request, response, stream, usage, and error objects remain Serviq-owned C-4 models.
3. The adapter receives only a resolved `AdapterContext` with provider, upstream model, and secret.
4. `context.provider` must equal `gemini`; a mismatched provider context fails closed before a provider call.
5. The adapter uses only `context.upstream_model`. It does not resolve `modelAlias` and does not accept an arbitrary provider model from caller content.
6. C-4 hard limits remain authoritative: maximum output tokens and timeout are validated before the adapter receives the request.
7. Required CI tests inject/mock the SDK boundary and make no real Gemini network calls.
8. A premium security review is required before the implementation PR can merge.

## Why this decision was made

`google-genai` is Google's current official Python SDK for the Gemini Developer API and provides the async generation, async streaming, structured-output, timeout, and typed configuration surfaces OPE-296 needs. Exact pinning keeps provider behavior reproducible, while keeping the SDK behind the existing adapter interface prevents Gemini-specific implementation details from spreading into Serviq domain or agent code.

Most importantly, this ADR resolves the ticket's architecture stop condition explicitly instead of allowing a feature implementation to choose a dependency implicitly.

## Consequences

### Positive

- OPE-296 is unblocked without modifying Contract C-4.
- Gemini can follow the same provider-boundary security model already used by OpenAI and Anthropic.
- CI remains deterministic and can use mocks/fakes only.
- Future SDK upgrades are reviewable dependency changes.
- Caller-controlled endpoints and hidden retries remain outside the adapter contract.

### Trade-offs

- Serviq takes responsibility for maintaining compatibility with the exact pinned SDK version.
- Gemini uses provider-specific role terminology (`model` rather than `assistant`) inside the adapter.
- Some model-specific capabilities may still be rejected explicitly when they cannot satisfy C-4.
- A stable public provider request ID may not always be available, so C-4 `requestId` can legitimately be `null`.

## Scope

This ADR approves only the Gemini SDK/transport rules required to implement OPE-296. It does not approve OpenRouter transport, model routing or fallback, connectivity-test model selection, model-configuration reference semantics, Vertex AI deployment, arbitrary base URLs, agent-runtime changes, or shared C-4 extensions.

## Evidence reviewed

- Official Google Gen AI Python SDK repository and package documentation.
- Official `google-genai` 2.17.0 release dated 2026-08-06.
- Official 2.17.0 package metadata declaring Python `>=3.10` and explicitly classifying Python 3.14.
- Official async `generate_content` and `generate_content_stream` documentation.
- Official SDK configuration documentation for system instructions, JSON structured output, HTTP timeout, and retry options.
