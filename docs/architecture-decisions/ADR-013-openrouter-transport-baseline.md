# ADR-013 — OpenRouter transport baseline for OPE-297

## Status

Accepted.

## Context

OPE-297 adds OpenRouter as another provider implementation behind Serviq Contract C-4. The ticket previously stopped correctly because the repository did not freeze which OpenRouter client/transport was allowed, who owned the upstream endpoint, or whether a caller could influence that endpoint.

This decision must preserve the same provider-neutral boundary used by OpenAI, Anthropic, and Gemini while avoiding a new arbitrary-proxy surface.

OpenRouter's current official documentation explicitly supports using the OpenAI SDK as a drop-in client by setting the SDK base URL to `https://openrouter.ai/api/v1`. The same documentation supports Chat Completions streaming and JSON Schema structured output through `response_format` for compatible models.

Serviq already pins and security-reviews `openai==2.53.0` for its OpenAI adapter. Reusing that existing, approved dependency is the smallest production change and avoids adding a second Python package only to call an OpenAI-compatible API surface.

## Decision

Serviq V1.2 will implement OpenRouter through the existing pinned OpenAI Python SDK:

- client dependency: `openai==2.53.0`;
- protocol surface: OpenAI-compatible Chat Completions;
- Serviq-owned base URL: `https://openrouter.ai/api/v1`;
- tenant credential: server-resolved OpenRouter BYOK key passed only through `AdapterContext`;
- model: validated `AdapterContext.upstream_model` only;
- timeout: already-validated C-4 `timeoutMs`;
- output-token budget: already-validated C-4 `maxOutputTokens`;
- retries: SDK retries disabled with `max_retries=0`;
- required CI tests: injected fake/mock client only, with no OpenRouter network request.

No additional OpenRouter Python dependency is approved by this ADR.

## Endpoint ownership and SSRF boundary

The OpenRouter base URL is a code-owned constant in the provider adapter. It is not accepted from:

- C-4 request JSON;
- query parameters;
- provider metadata supplied by a tenant;
- model configuration fields;
- agent configuration;
- arbitrary environment variables.

The adapter must construct its client with the exact Serviq-owned OpenRouter base URL. OPE-297 is not authorized to add a generic `baseUrl`, `endpoint`, proxy destination, or equivalent field to C-4.

This preserves the rule that tenants may choose an approved provider connection and validated model configuration, but cannot turn the LLM Gateway into an arbitrary outbound HTTP proxy.

## Model ownership

C-4 exposes `modelAlias`, not a raw upstream provider model. Upstream-model resolution happens before the provider adapter.

The OpenRouter adapter therefore sends exactly `AdapterContext.upstream_model` to the SDK. It must not:

- derive a model from user message text;
- accept a second raw model field;
- rewrite the validated model into a fallback list;
- automatically substitute an OpenRouter `:free`, `:nitro`, or other variant;
- add provider fallbacks or routing preferences.

OpenRouter's provider-routing features remain outside OPE-297 unless separately frozen later.

## Message translation

OpenRouter's Chat Completions surface accepts the C-4 roles used by the existing OpenAI adapter:

- `system` -> `system`;
- `user` -> `user`;
- `assistant` -> `assistant`.

Message order and content are preserved. The adapter does not inject a hidden system message, rewrite customer text, or add provider-routing instructions.

## Structured output

C-4 already supports `responseSchema`.

When present, the adapter will use OpenRouter's OpenAI-compatible JSON Schema response format:

- `type = json_schema`;
- a Serviq-owned response-format name;
- `strict = true`;
- schema = the already validated C-4 schema.

OpenRouter documents structured outputs only for compatible models. If the validated upstream model/provider route rejects this capability, the adapter must return the normalized C-4 invalid-request error rather than silently dropping `responseSchema`.

Structured response text must be parsed into Serviq's own `structured` dictionary before crossing the adapter boundary.

For streaming structured output, JSON fragments may be buffered until the stream completes and then parsed into a provider-neutral `structuredDelta`, matching the existing provider-neutral C-4 pattern. Provider SDK chunk objects must never escape.

## Streaming

Streaming uses Chat Completions with `stream=True` and requests usage metadata using the same OpenAI-compatible stream option already used by Serviq's OpenAI adapter.

The adapter must:

- preserve chunk order;
- preserve provider-generated whitespace;
- emit only `GatewayStreamEvent` objects;
- normalize finish reason, request ID, and usage where provided;
- fail safely if a stream ends without meaningful terminal metadata.

No OpenRouter-specific stream event type becomes part of C-4.

## Retry and timeout ownership

The request-scoped `AsyncOpenAI` client is constructed with:

- the fixed OpenRouter base URL;
- the resolved OpenRouter API key;
- the C-4 timeout budget;
- `max_retries=0`.

Serviq owns retry, fallback, and orchestration behavior above the provider adapter. The adapter must not enable OpenRouter model fallbacks, SDK retries, or hidden replay behavior.

## Provider-specific headers

OpenRouter documents optional attribution headers such as `HTTP-Referer` and `X-OpenRouter-Title`.

OPE-297 will not send caller-controlled provider-specific headers. V1.2 does not require app attribution to satisfy C-4, so the initial adapter will omit optional OpenRouter attribution/routing headers rather than creating new configuration or shared-contract fields.

A future architecture decision may add server-owned attribution metadata if product requirements need it.

The adapter must not expose or forward arbitrary inbound headers to OpenRouter.

## Error normalization

The OpenAI SDK may surface OpenRouter HTTP failures through its standard exception hierarchy. OPE-297 must translate those failures into only the existing C-4 categories:

- HTTP 401/403 or SDK authentication/permission failure -> `PROVIDER_AUTH_FAILED`;
- HTTP 429 -> `PROVIDER_RATE_LIMITED`;
- SDK/transport timeout or HTTP 408 -> `PROVIDER_TIMEOUT`;
- connection failure, HTTP 5xx, or unknown provider failure -> `PROVIDER_UNAVAILABLE`;
- applicable HTTP 4xx invalid model/schema/request failures -> `PROVIDER_INVALID_REQUEST`.

Normalized messages are Serviq-authored fixed strings. Raw OpenRouter bodies, HTML error pages, response headers, SDK exception text, and API keys must not become C-4 output or logs produced by the adapter.

## SDK-type containment

Although OpenRouter uses the same client dependency as the OpenAI adapter, it remains a separate provider adapter.

Provider SDK types may exist only inside the OpenRouter adapter and its tests. The public boundary remains:

- `GatewayRequest`;
- `GatewayResponse`;
- `GatewayStreamEvent`;
- `GatewayUsage`;
- `GatewayProviderError`.

The adapter must set the normalized provider value to `openrouter`, not `openai`.

## Dependency and security implications

No new third-party runtime dependency is introduced by this architecture choice. OPE-296 already extended the repository security workflow so LLM Gateway dependencies are included in the explicit Python vulnerability audit.

A later upgrade to the pinned OpenAI SDK affects both the OpenAI and OpenRouter adapters and therefore requires regression tests for both provider implementations.

## External documentation reviewed

Decision reviewed against current OpenRouter documentation on 2026-08-18:

- OpenRouter Quickstart — OpenAI SDK drop-in usage and fixed API base URL;
- OpenRouter OpenAI SDK integration guide;
- OpenRouter Streaming documentation;
- OpenRouter Structured Outputs documentation.

## Scope exclusions

ADR-013 does not approve:

- arbitrary OpenRouter endpoints;
- caller-supplied base URLs;
- OpenRouter native/agent SDK dependencies;
- model fallback arrays;
- provider preference/routing controls;
- plugins;
- web search;
- tool use;
- OpenRouter-specific C-4 fields;
- agent-runtime changes;
- model alias behavior changes;
- secret-store changes.

Those require separate product/architecture decisions if needed.

## Result

OPE-297's transport/client stop condition is resolved once this ADR is merged. Runtime implementation may then proceed without changing Contract C-4.