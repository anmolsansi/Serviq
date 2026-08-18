# OPE-296 — Gemini adapter premium security review

## Scope

This review covers the Gemini generation and streaming adapter implemented for OPE-296 behind Serviq Contract C-4. It evaluates dependency trust, BYOK credential handling, provider selection, endpoint control, message translation, timeout/retry behavior, structured output, streaming, error normalization, SDK-type containment, cleanup, and test isolation.

It does **not** add or review provider routing, model alias resolution, provider connectivity testing, agent runtime logic, fallback routing, tenant secret persistence, or arbitrary Google Cloud/Vertex configuration.

## Architecture prerequisite

OPE-296 originally stopped because the repository had no approved Gemini dependency. That stop condition was resolved by `docs/architecture-decisions/ADR-012-gemini-sdk-baseline.md`, merged through PR #136.

ADR-012 approves exactly:

- official Google package `google-genai==2.17.0`;
- Gemini Developer API mode;
- tenant BYOK supplied by the server through `AdapterContext`;
- one upstream attempt/no hidden SDK retries;
- existing C-4 token and timeout limits;
- provider-local Gemini types only;
- mock/fake-only required CI tests.

The implementation therefore follows a reviewed architecture decision rather than selecting a provider SDK inside feature code.

## Assets at risk

The adapter touches several sensitive or business-critical values:

- tenant-owned Gemini API keys;
- customer/support conversation text sent to the selected Gemini model;
- optional JSON response schemas;
- resolved upstream model names;
- generated response content;
- request identifiers and token usage metadata;
- provider errors that could contain raw Google response bodies, keys, URLs, or internal diagnostics.

The adapter is designed so only the minimum values required for the provider call cross the provider boundary.

## Dependency boundary

`google-genai==2.17.0` is exact-pinned in `services/llm-gateway/pyproject.toml`. Gemini imports are isolated to `app.adapters.gemini` and its test module.

The public request, response, stream, usage, and error types remain Serviq-owned objects from `app.schemas.c4`. No Google SDK response, candidate, content, usage, error, or stream object is returned to domain or agent code.

This separation matters because an SDK upgrade can change provider-specific classes without forcing Serviq's internal product contract to change.

## BYOK credential handling

The Gemini API key is accepted only through `AdapterContext.api_key`, which is a server-resolved `SecretStr` populated above the adapter boundary.

The adapter does not read provider keys from:

- C-4 request JSON;
- headers supplied by end users;
- query parameters;
- model alias fields;
- provider metadata columns;
- arbitrary environment variables.

The plaintext key is extracted only to construct the official Google client. It is never inserted into a `GatewayResponse`, `GatewayStreamEvent`, or normalized error.

If the resolved key is missing or blank, the adapter fails before any provider call with `PROVIDER_AUTH_FAILED`.

`AdapterContext.__repr__` already redacts the secret, preserving the existing gateway security convention.

## Provider-context binding

`GeminiAdapter` requires `context.provider == GatewayProvider.GEMINI`.

If routing accidentally supplies an OpenAI, Anthropic, or OpenRouter context, the adapter returns `PROVIDER_INVALID_REQUEST` before creating a Google client or making a network request.

The adapter also ignores `request.model_alias` for provider selection. It sends only the already-resolved `context.upstream_model`. This prevents a caller from using the Gemini adapter as a free-form model or endpoint proxy.

## Endpoint and enterprise-routing control

The approved deployment mode is the Gemini Developer API. The default factory explicitly constructs:

`genai.Client(api_key=<resolved key>, enterprise=False)`

The explicit `enterprise=False` is security-relevant. It prevents environment configuration such as `GOOGLE_GENAI_USE_ENTERPRISE` from changing the provider target underneath a tenant BYOK request.

The C-4 request cannot provide:

- a base URL;
- a Google Cloud project;
- a location/region;
- Vertex/enterprise mode;
- custom transport settings.

Therefore OPE-296 does not create an SSRF-style arbitrary endpoint surface or let tenant input redirect provider traffic.

## Request budgets and retry ownership

C-4 validates the hard platform limits before the request reaches the adapter:

- maximum output tokens: 1,500;
- maximum timeout: 20,000 ms.

The adapter forwards those already-bounded values through `GenerateContentConfig`.

Per-request `HttpOptions` uses the C-4 timeout and `HttpRetryOptions(attempts=1)`. In the Google SDK, one attempt means no hidden retry loop. This is deliberate because retry/fallback policy belongs to Serviq above the provider adapter.

Without this control, the SDK could perform additional provider calls that exceed the visible time/cost budget or duplicate generation without Serviq knowing.

## Message translation

Gemini's conversation roles differ slightly from C-4. OPE-296 handles that difference only inside the adapter:

- leading C-4 `system` messages are joined in original order and passed as `system_instruction`;
- C-4 `user` maps to Gemini `user`;
- C-4 `assistant` maps to Gemini `model`;
- message text is not trimmed, rewritten, or augmented with hidden prompts.

A system message appearing after the conversation has started is rejected with `PROVIDER_INVALID_REQUEST` instead of being silently reordered.

A system-only request is also rejected explicitly because it cannot produce a valid provider conversation while preserving C-4 meaning.

Importantly, message validation/translation is performed before the provider client is constructed. Invalid provider-specific layouts therefore fail without unnecessarily exposing the resolved key to SDK client construction.

## Structured output

When `responseSchema` is present, the adapter uses Gemini's native structured-output configuration:

- response MIME type `application/json`;
- `response_json_schema` set from the already-validated C-4 schema.

The provider's JSON text is parsed into `dict[str, JsonValue]` before it crosses the adapter boundary.

Malformed or missing provider JSON is not passed downstream. It becomes a fixed `PROVIDER_UNAVAILABLE` failure because the provider did not produce a usable response to a valid request.

For streaming structured output, partial provider chunks are buffered until completion and then parsed. This avoids exposing invalid partial JSON as if it were a valid C-4 structured object.

If Gemini rejects a requested schema/capability, the SDK error is normalized to `PROVIDER_INVALID_REQUEST`; the adapter never silently ignores `responseSchema` and falls back to unrestricted text.

## Streaming integrity

Plain-text streaming yields each provider text chunk in order through `GatewayStreamEvent.contentDelta`.

No `.strip()` or normalization is applied to generated text, so meaningful leading/trailing whitespace is preserved. This follows the provider-output C-4 behavior already established for OpenAI and Anthropic.

Only C-4 fields are emitted:

- content delta or structured delta;
- finish reason;
- usage;
- request ID when available.

Raw `GenerateContentResponse` stream chunks never leave the adapter.

An empty stream with no terminal/provider metadata is treated as `PROVIDER_UNAVAILABLE` instead of being reported as a successful empty answer.

## Response metadata minimization

The adapter returns only metadata frozen by C-4:

- provider = `gemini`;
- resolved upstream model;
- input/output token counts when supplied;
- finish reason;
- provider response ID when supplied.

It does not expose provider safety metadata, raw candidate structures, response headers, SDK transport data, Google-specific fields, or internal exception details.

## Error normalization and secret redaction

Every external failure is converted into one of the existing five C-4 categories:

- 401/403 -> `PROVIDER_AUTH_FAILED`;
- 429 -> `PROVIDER_RATE_LIMITED`;
- provider HTTP 408, `httpx` timeout, or local timeout -> `PROVIDER_TIMEOUT`;
- provider 5xx or transport failure -> `PROVIDER_UNAVAILABLE`;
- other applicable 4xx/provider validation failures -> `PROVIDER_INVALID_REQUEST`.

Normalized messages are fixed Serviq-authored text.

The implementation never incorporates:

- `str(provider_exception)`;
- Google error details;
- provider response JSON;
- provider response headers;
- API key material;
- arbitrary upstream HTML/text bodies.

Tests deliberately construct SDK errors containing representative secret/raw-provider text and verify none of it appears in the resulting C-4 error.

## Client resource cleanup

The SDK client is request-scoped. Both asynchronous and synchronous client resources are closed after success or failure.

Cleanup exceptions are suppressed deliberately. A cleanup failure must not replace the already normalized provider result with a raw SDK/transport exception that could bypass the adapter's error boundary.

## Logging exposure

The Gemini adapter itself does not log the API key, SDK exception, provider response, or raw request body.

This is intentional. Higher-level gateway telemetry may log Serviq-owned correlation metadata, but provider-secret/provider-error logging is not introduced in OPE-296.

## Test isolation

`services/llm-gateway/tests/test_gemini_adapter.py` injects a fake Google client through the adapter's client-factory seam.

The tests do not invoke `generate_content` or `generate_content_stream` on a real network client. They only use local fake objects plus official SDK error/type definitions where useful for contract compatibility.

Coverage includes:

- non-stream success;
- message/role/system translation;
- exact timeout and one-attempt retry configuration;
- structured non-stream output;
- text streaming with whitespace/order preservation;
- structured streaming;
- auth failure;
- rate limit;
- timeout;
- provider outage;
- invalid request;
- raw secret/provider-error redaction;
- late-system-message rejection;
- system-only unsupported behavior;
- malformed structured output;
- missing key;
- mismatched provider context;
- incorrect streaming path;
- empty stream without terminal metadata;
- provider-neutral return types.

No required CI test spends Gemini credits or depends on external network/provider availability.

## Security review conclusion

OPE-296 keeps Gemini behind the same Serviq-owned C-4 trust boundary used by the other provider adapters. The tenant key remains server-resolved, enterprise/custom endpoint control is unavailable to callers, provider retries cannot silently multiply calls, bounded C-4 request limits remain authoritative, provider objects stay local, malformed provider output fails closed, and raw upstream exceptions/secret material are replaced with fixed C-4 errors.

The implementation is suitable to merge only after the repository's lint, strict type checking, automated tests, dependency/security workflows, and PR review all pass. This document records the design review; CI/Security status must still be checked on the final PR head before OPE-296 is marked Done.
