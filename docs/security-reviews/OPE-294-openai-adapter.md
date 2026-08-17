# OPE-294 — OpenAI adapter security review

## Scope

This review covers the OpenAI generation/streaming adapter behind Serviq Contract C-4. It covers BYOK credential handling, provider request construction, timeout behavior, structured-output translation, streaming, error normalization, SDK-type containment, and test isolation. It does not add provider routing, model alias resolution, secret persistence, retries/fallback, or agent-runtime behavior.

## Assets at risk

- Tenant-owned OpenAI API keys.
- Customer/support message content sent to the selected provider.
- Structured response schemas supplied through C-4.
- Provider response content and streaming chunks.
- Provider request identifiers and usage metadata.
- Error details that could otherwise expose upstream response bodies or credentials.

## Dependency trust boundary

ADR-011 freezes the official OpenAI Python SDK at `openai==2.53.0`. The adapter imports SDK types only inside `app.adapters.openai` and its tests. Serviq's public request, response, stream, and error objects remain the provider-neutral models in `app.schemas.c4`.

The adapter therefore acts as a translation boundary rather than allowing OpenAI objects to spread into business logic. A later SDK upgrade requires an explicit dependency review instead of changing behavior silently.

## BYOK key handling

The adapter does not read OpenAI keys from request JSON, query parameters, arbitrary environment variables, or relational provider metadata. It receives a server-resolved `SecretStr` only through `AdapterContext`, which is populated above this adapter after tenant provider/model resolution.

The plaintext value is extracted only when constructing the official SDK client. The adapter never returns it, includes it in C-4 objects, or puts it into an exception message. `AdapterContext.__repr__` already redacts the secret.

If the context contains no API key or a blank key, the adapter fails closed with `PROVIDER_AUTH_FAILED` before creating an SDK client.

## Provider-context binding

`OpenAIAdapter` requires `context.provider == openai`. Supplying an Anthropic/Gemini/OpenRouter context is rejected as `PROVIDER_INVALID_REQUEST` before an upstream call. This prevents a routing mistake from sending another provider's resolved credential/model configuration to OpenAI.

The adapter also does not interpret `modelAlias`. It uses only the already resolved `context.upstream_model`. Model alias lookup remains a separate server-side responsibility.

## Bounded requests and hidden retries

C-4 already validates the hard limits `maxOutputTokens <= 1500` and `timeoutMs <= 20000`. The adapter forwards those bounded values to the official SDK.

The request-scoped `AsyncOpenAI` client is created with `max_retries=0`. This is deliberate: automatic SDK retries could consume more time/cost than the caller's visible C-4 budget and could duplicate a request without Serviq's higher-level routing/fallback layer knowing. Retry and fallback policy therefore remains an explicit Serviq responsibility.

## Message meaning

System, user, and assistant messages are forwarded in the same order and with their C-4 role/content. The adapter does not inject hidden prompts, rewrite customer text, merge roles, or interpret magic control strings.

This matters both for correctness and for security review: provider-specific behavior cannot secretly alter the application policy boundary inside the adapter.

## Structured output

When `responseSchema` is present, the adapter uses the official SDK's JSON Schema response-format boundary and marks the schema strict. Returned JSON text is parsed into the Serviq-owned `structured` object before leaving the adapter.

If the provider returns missing or malformed structured output, the adapter fails with a safe normalized provider error instead of returning a raw SDK response or passing malformed provider objects to downstream agents.

The caller-supplied schema is already bounded by the C-4 request contract. OPE-294 does not add provider-specific shared fields or relax schema validation.

## Streaming text integrity

The prerequisite C-4 correction in PR #123 separates provider-output validation from request identifier normalization. `GatewayStreamEvent.contentDelta` now preserves leading/trailing whitespace, so a provider chunk such as `" world"` cannot silently become `"world"`.

The adapter yields normalized C-4 events in provider order and emits only content deltas plus terminal finish/usage/request metadata. Raw `ChatCompletionChunk` objects never leave the adapter.

## Error normalization and data minimization

The adapter maps official SDK failures into only the five C-4 categories:

- authentication/permission -> `PROVIDER_AUTH_FAILED`;
- HTTP 429 -> `PROVIDER_RATE_LIMITED`;
- SDK timeout -> `PROVIDER_TIMEOUT`;
- connection/5xx/provider failures -> `PROVIDER_UNAVAILABLE`;
- invalid/not-found/unprocessable provider requests -> `PROVIDER_INVALID_REQUEST`.

Normalized messages are fixed Serviq-written strings. The upstream exception text, HTTP body, headers, provider stack object, and credential are intentionally discarded. Tests construct an authentication failure whose raw SDK exception contains representative secret material and verify the normalized error contains none of it.

## Request/response data exposure

An OpenAI call necessarily sends the selected C-4 messages, selected upstream model, token bound, and optional structured response schema to OpenAI. OPE-294 does not send tenant IDs, provider `secretRef`, internal permissions, membership records, database metadata, or unrelated Serviq state.

Provider request IDs and usage counts may return through C-4 because those fields are explicitly frozen in the architecture for debugging/accounting. Raw provider response bodies are not retained by the adapter.

## Network behavior in tests

Required tests inject a fake official-SDK client through the adapter's client-factory seam. They never create the real `AsyncOpenAI` network client and never make a paid provider request. Representative provider exceptions are instantiated locally and passed into normalization tests.

This keeps CI deterministic, free, and independent of external provider availability while still testing the official SDK exception classes and Serviq adapter contract.

## Review conclusion

OPE-294 keeps the tenant OpenAI key server-side, binds the adapter to the resolved OpenAI provider context, preserves the C-4 timeout/token budget, disables hidden SDK retries, contains all provider SDK objects inside the adapter, preserves streaming text exactly, and replaces upstream errors with fixed provider-neutral failures. No raw key, SDK response, exception body, or provider-specific public type is intentionally exposed beyond the adapter boundary.
