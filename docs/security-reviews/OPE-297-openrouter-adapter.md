# OPE-297 — OpenRouter adapter security review

## Scope

This review covers the OpenRouter generation/streaming adapter behind Serviq Contract C-4. It covers outbound endpoint control, tenant BYOK credential handling, validated model ownership, OpenAI-compatible SDK usage, timeout/retry behavior, structured-output translation, streaming, OpenRouter in-band errors, response/error data minimization, resource cleanup, and test isolation.

It does not add model routing, provider fallbacks, OpenRouter plugins, arbitrary endpoint support, secret persistence, agent-runtime behavior, or OpenRouter-only fields to C-4.

## Assets at risk

- Tenant-owned OpenRouter API keys.
- Customer/support message content sent to the selected OpenRouter model.
- Structured response schemas supplied through C-4.
- Provider response content and stream chunks.
- Provider request IDs and token-usage metadata.
- Internal network reachability if callers could control the provider endpoint.
- Raw provider error bodies, which may contain upstream implementation details or accidentally echoed request data.

## Architecture prerequisite

ADR-013 freezes the OpenRouter transport before runtime code is allowed to exist.

The adapter uses Serviq's existing exact SDK pin:

`openai==2.53.0`

OpenRouter officially supports using the OpenAI SDK against its OpenAI-compatible API. Serviq therefore avoids adding another runtime dependency while still maintaining a separate provider implementation.

The transport decision is intentionally not inferred from code. It is version-controlled in `docs/architecture-decisions/ADR-013-openrouter-transport-baseline.md` and was merged through PR #141 after CI and Security passed.

## Fixed outbound destination

The most important OPE-297 security rule is that tenants may choose a provider connection and validated model, but not an arbitrary network destination.

The adapter owns this constant:

`https://openrouter.ai/api/v1`

The destination does not come from:

- C-4 request JSON;
- a query parameter;
- user message content;
- `modelAlias`;
- `model_configurations.upstream_model`;
- provider metadata;
- an agent configuration;
- an arbitrary environment variable.

The default client factory passes the constant directly as the SDK `base_url`.

C-4 uses Pydantic `extra="forbid"`, so request fields such as `baseUrl` and `endpoint` are rejected rather than ignored. OPE-297 tests explicitly attempt to provide an attacker-controlled public URL and a link-local metadata-style URL and verify the C-4 request is invalid.

This prevents the adapter from becoming a generic outbound HTTP proxy or SSRF-like primitive.

## BYOK credential handling

The adapter does not read OpenRouter keys from request JSON, query parameters, model configuration, or arbitrary environment variables.

It receives only the `SecretStr` already resolved by Serviq through `AdapterContext` after the tenant provider connection has been selected above the adapter boundary.

The plaintext secret is extracted only to construct the request-scoped SDK client. It is not returned in C-4 objects, used as a model identifier, copied into provider metadata, or intentionally logged.

Missing or blank credentials fail closed as `PROVIDER_AUTH_FAILED` before a provider request is created.

## Provider-context binding

`OpenRouterAdapter` requires:

`context.provider == GatewayProvider.OPENROUTER`

A routing error that sends an OpenAI, Anthropic, or Gemini context into this adapter is rejected before the OpenRouter client is created.

This matters because provider connections represent separate tenant trust boundaries. A resolved credential for one provider must never be accidentally sent to another provider endpoint.

## Model ownership

The adapter never accepts a raw upstream model from C-4 request content.

C-4 contains `modelAlias`; validated model resolution occurs before the provider adapter. The adapter sends exactly:

`context.upstream_model`

It does not:

- parse a model name from user text;
- accept a second provider model field;
- create fallback model arrays;
- append OpenRouter variants such as `:free` or `:nitro`;
- add provider-routing preferences;
- substitute a different model when the requested one fails.

Tests verify the exact validated upstream-model string reaches the mocked SDK call.

## No provider-routing escape hatch

OpenRouter supports powerful provider-specific routing features, fallback arrays, plugins, metadata, and optional headers. OPE-297 deliberately does not expose those features.

The adapter does not pass `extra_body`, caller-controlled default headers, plugin configuration, provider preferences, fallback models, or a caller-controlled `X-OpenRouter-Metadata` setting.

This keeps OPE-297 a provider adapter rather than a second routing/orchestration system inside the gateway.

## Optional attribution headers

OpenRouter documents optional application-attribution headers such as `HTTP-Referer` and `X-OpenRouter-Title`.

The initial V1.2 adapter does not accept those values from callers and does not create new shared configuration solely for attribution. If Serviq later wants OpenRouter dashboard attribution, a server-owned configuration can be introduced through a separate reviewed change.

Arbitrary inbound HTTP headers are never forwarded to OpenRouter.

## Timeout and retry control

C-4 already validates the maximum provider timeout and output-token budget.

The OpenRouter client is built with:

- the C-4 timeout converted to seconds;
- `max_retries=0`.

The generation call also receives the request timeout and `max_completion_tokens` explicitly.

Disabling SDK retries prevents hidden replay underneath Serviq. Hidden retries could increase provider cost, exceed the caller-visible time budget, duplicate generation, and interfere with later Serviq-owned fallback/orchestration logic.

## Structured output

When C-4 supplies `responseSchema`, the adapter uses OpenRouter's OpenAI-compatible JSON Schema response format with strict mode enabled.

The returned JSON text is parsed into Serviq's own `structured` dictionary before it crosses the provider boundary.

Malformed or missing structured output fails closed. The raw provider object is never treated as trusted structured data.

For streaming structured output, partial JSON text is buffered until the provider stream completes and is then parsed into a C-4 `structuredDelta`. This avoids exposing provider SDK chunks or handing downstream code incomplete JSON as if it were a complete structured object.

## Streaming text integrity

For normal text streaming, content chunks are yielded in provider order through `GatewayStreamEvent.contentDelta`.

The C-4 output model preserves provider-generated whitespace. A chunk such as `" world"` stays `" world"`; it is not trimmed into `"world"`.

Finish reason, request ID, and usage metadata are normalized into Serviq-owned terminal event fields where OpenRouter provides them.

A stream that ends without meaningful terminal metadata fails safely rather than pretending the request completed normally.

## OpenRouter in-band error handling

OpenRouter can return some provider failures after generation has already begun. Once HTTP 200 and partial stream content have been sent, the failure may arrive inside the stream as an error object rather than as a normal HTTP error status.

A naive OpenAI-compatible adapter could miss that distinction and accidentally treat partial output as a successful response.

OPE-297 explicitly checks for embedded OpenRouter error data on completion choices and stream chunks before normalizing the response.

The adapter inspects only the minimum information required to classify the failure:

- numeric error code;
- stable `error_type` when present.

It does not propagate OpenRouter's raw `message`, provider code, metadata object, HTML error page, or provider routing details.

Typed OpenRouter errors are normalized as follows:

- authentication/permission -> `PROVIDER_AUTH_FAILED`;
- rate limit -> `PROVIDER_RATE_LIMITED`;
- timeout -> `PROVIDER_TIMEOUT`;
- provider overloaded/unavailable/server/unmapped -> `PROVIDER_UNAVAILABLE`;
- other typed validation/request failures -> `PROVIDER_INVALID_REQUEST`.

Tests include both mid-stream and non-stream embedded failures and verify partial content is not returned as a successful C-4 result.

## Standard SDK error normalization

Errors that arrive before a response stream is committed are surfaced through the OpenAI SDK exception hierarchy.

The adapter maps those into the same five C-4 categories used by the other providers:

- authentication/permission -> `PROVIDER_AUTH_FAILED`;
- HTTP 429 -> `PROVIDER_RATE_LIMITED`;
- timeout/HTTP 408 -> `PROVIDER_TIMEOUT`;
- connection/5xx -> `PROVIDER_UNAVAILABLE`;
- applicable 4xx invalid model/schema/request failures -> `PROVIDER_INVALID_REQUEST`.

Normalized messages are fixed Serviq-authored strings.

## Raw provider-error and secret containment

OpenRouter can sit in front of many different upstream model providers, so a raw failure may contain provider-specific details that Serviq should not expose.

Tests construct representative SDK and in-band failures containing:

- fake API-key text;
- raw provider messages;
- HTML-like error descriptions;
- partial generated content.

The normalized exception contains none of those values.

This reduces the chance that provider implementation details, upstream error pages, request content, or credential material escape through an API response or later error log.

## SDK-type containment

Although the OpenRouter adapter reuses the OpenAI SDK as its transport, it does not return an OpenAI SDK type.

The public boundary remains Serviq-owned:

- `GatewayResponse`;
- `GatewayStreamEvent`;
- `GatewayUsage`;
- `GatewayProviderError`.

The normalized provider identity is `openrouter`, not `openai`.

This is why OPE-297 implements a separate `OpenRouterAdapter` rather than aliasing or directly reusing `OpenAIAdapter`.

## Request-scoped client cleanup

The adapter closes its request-scoped async SDK client after both successful and failed provider operations.

Cleanup exceptions are suppressed so a socket/client-close problem cannot replace an already safe normalized provider result with an SDK-specific exception.

## Dependency security

OPE-297 adds no new runtime dependency. It reuses the already pinned `openai==2.53.0` package.

During OPE-296, Serviq's Security workflow was extended so LLM Gateway dependencies are explicitly included in the Python vulnerability audit. Therefore the transport used by OPE-297 is covered by:

- dependency vulnerability auditing;
- Trivy filesystem/configuration scanning;
- CodeQL Python analysis;
- Gitleaks repository-history scanning.

## Network behavior in tests

All required provider tests use an injected fake client and fake async stream.

The tests do not:

- require an OpenRouter account;
- use a real API key;
- make an OpenRouter network request;
- spend provider credits;
- depend on OpenRouter uptime.

The default-client security test monkeypatches the `AsyncOpenAI` constructor and verifies the exact fixed base URL and `max_retries=0` values without opening a provider connection.

## Review conclusion

OPE-297 keeps OpenRouter behind the existing C-4 trust boundary, fixes the outbound destination in code, accepts only server-resolved tenant credentials and validated models, disables hidden retries, handles both normal SDK failures and OpenRouter's in-band provider failures, discards raw provider details, and returns only Serviq-owned response/error types.

The adapter does not introduce an arbitrary endpoint control, OpenRouter routing/plugin surface, new secret path, or provider-specific public contract.