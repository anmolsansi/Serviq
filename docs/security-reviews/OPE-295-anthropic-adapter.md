# OPE-295 — Anthropic adapter security review

## Scope

This review covers the Anthropic generation/streaming adapter behind Serviq Contract C-4. It covers tenant BYOK handling, system/message translation, bounded request construction, structured output, raw streaming-event normalization, provider errors, SDK-type containment, and mocked test behavior. It does not implement routing, model alias lookup, provider fallback, secret persistence, or agent runtime.

## Dependency boundary

ADR-011 freezes the official Anthropic Python SDK at `anthropic==0.121.0`. Anthropic SDK classes are imported only inside `app.adapters.anthropic` and adapter tests. Public callers receive only Serviq-owned C-4 models and `GatewayProviderError`.

An SDK upgrade is therefore an explicit reviewed dependency event instead of an implicit provider behavior change.

## BYOK credential handling

The adapter receives a server-resolved `SecretStr` through `AdapterContext`. It never accepts an API key from C-4 request JSON, message content, query parameters, model aliases, or relational metadata.

The plaintext key is extracted only to construct the request-scoped official SDK client. It is never copied into a gateway response, stream event, normalized error, or log message. Missing/blank keys fail closed as `PROVIDER_AUTH_FAILED` before an SDK client is created.

`AdapterContext.__repr__` redacts the secret by design, reducing accidental debug-log exposure.

## Provider/model binding

`AnthropicAdapter` requires `context.provider == anthropic`. A context resolved for OpenAI, Gemini, or OpenRouter is rejected before an upstream request. This reduces the risk of sending one provider's tenant credential or model configuration to another provider.

The adapter does not resolve `modelAlias`. It receives only the already resolved `context.upstream_model`, keeping tenant model selection in the server-side routing/configuration layer.

## System prompt translation

Anthropic's Messages API represents system instructions outside the normal user/assistant message list. The adapter therefore moves only **leading** C-4 system messages into the top-level Anthropic `system` field, preserving their order with explicit separation. User/assistant turns stay in their original order.

A system message appearing after conversation history has begun is rejected with `PROVIDER_INVALID_REQUEST`. The adapter does not silently reorder it, drop it, or convert it to a user message. A request containing only system instructions is also rejected because Anthropic requires a conversational message.

This explicit failure behavior prevents provider-specific translation from changing the meaning of the application prompt without the caller knowing.

## Bounded calls and retry ownership

C-4 already constrains `maxOutputTokens` to at most 1500 and `timeoutMs` to at most 20000. The adapter forwards those validated values as Anthropic `max_tokens` and request timeout.

The request-scoped `AsyncAnthropic` client uses `max_retries=0`. Hidden SDK retries would otherwise make duration/cost exceed the caller-visible budget and could duplicate requests without Serviq's higher-level retry/fallback layer knowing. Retry/fallback policy remains explicit outside this adapter.

## Structured output

When `responseSchema` is present, the adapter uses Anthropic's official `output_config.format` JSON Schema boundary. Non-stream responses are parsed into the Serviq-owned `structured` dictionary.

For structured streaming, Anthropic's JSON text deltas are buffered inside the adapter and emitted as a provider-neutral `structuredDelta` only after the JSON object validates. This prevents downstream code from depending on provider JSON tokenization while still supporting C-4's stream mode.

Missing/malformed structured output fails safely as `PROVIDER_UNAVAILABLE`; raw provider content or SDK objects do not escape.

## Streaming integrity

The adapter consumes raw Anthropic message events and emits only C-4 stream events. Text deltas are yielded in exact provider order and retain leading/trailing whitespace because the C-4 provider-output models were corrected in PR #123 not to trim generated text.

The adapter keeps message ID from `message_start`, output usage and stop reason from `message_delta`, and emits those values only in the normalized terminal event. Raw `RawMessageStreamEvent` objects never cross the adapter boundary.

## Error normalization

Expected Anthropic failures collapse into the five C-4 categories:

- authentication/permission -> `PROVIDER_AUTH_FAILED`;
- HTTP 429 -> `PROVIDER_RATE_LIMITED`;
- SDK timeout -> `PROVIDER_TIMEOUT`;
- connection failures, 5xx/529/504 responses, and generic provider failures -> `PROVIDER_UNAVAILABLE`;
- invalid 4xx request states -> `PROVIDER_INVALID_REQUEST`.

For generic `APIStatusError`, unknown non-4xx statuses are treated as unavailable rather than exposing or interpreting the provider response body. Normalized messages are fixed Serviq-written strings. Upstream exception text, response bodies, headers, stack objects, and credential data are discarded.

Tests construct representative SDK exceptions containing fake secret/raw-body material and verify none appears in the normalized error.

## Provider data exposure

A real Anthropic call necessarily receives the selected system instructions, user/assistant conversation, upstream model, output-token limit, optional response schema, and timeout. This adapter does not add tenant IDs, internal role/capability data, database metadata, provider `secretRef`, or unrelated application state to the provider request.

Normalized response exposure is limited to C-4 content/structured output, upstream model, request ID, stop reason, and token usage. Raw response objects are not returned.

## CI and paid-network isolation

Required adapter tests inject a fake official-SDK client through the client-factory seam. They do not create a real network client, use a real API key, or make paid Anthropic calls. Official SDK exception classes are instantiated locally to exercise normalization behavior.

This makes CI deterministic and free while still testing Serviq's contract against the approved SDK surface.

## Review conclusion

OPE-295 keeps Anthropic credentials server-side, preserves C-4 conversation meaning as far as the Anthropic Messages API can represent it, fails explicitly when it cannot, honors bounded token/time budgets, disables hidden retries, preserves streamed text, contains all Anthropic SDK objects inside the adapter, and exposes only safe provider-neutral errors and C-4 outputs.
