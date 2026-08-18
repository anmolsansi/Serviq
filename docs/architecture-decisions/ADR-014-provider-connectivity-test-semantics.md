# ADR-014 — Provider connectivity-test semantics for OPE-298

## Status

Accepted.

## Context

OPE-298 implements the frozen public endpoint:

```text
POST /api/v1/providers/{providerConnectionId}/test
```

The endpoint exists so a tenant administrator can check whether a stored Bring Your Own Key (BYOK) provider connection can make one small model request without exposing the key and without turning the API into a general-purpose completion proxy.

The public route, provider enum, provider status enum, provider-management permission, Contract C-4 error vocabulary, and two provider-test rate limits were already frozen in `docs/ARCHITECTURE.md`. The four provider adapters are also now implemented behind C-4.

The original OPE-298 repository audit correctly stopped because two important details were not yet frozen:

1. which upstream model Serviq itself chooses for a connectivity test; and
2. what persisted provider status means when a test fails for a temporary reason such as provider rate limiting, a timeout, or an upstream outage.

There was also no narrow API-to-LLM-Gateway invocation contract for this administrative health check. Reaching directly into the LLM Gateway package from the API would couple two deployable services and would move provider SDK knowledge into the API. Sending a normal caller-controlled C-4 payload over HTTP would expose model and prompt selection where the ticket explicitly forbids it.

This ADR resolves those gaps without changing the public provider API or Contract C-4.

## Decision summary

Serviq will implement provider connectivity testing as a narrow administrative control path with these rules:

- the public endpoint accepts **no request body**;
- the provider is read only from the stored `provider_connections.provider` value;
- the credential is read only through the tenant secret-store adapter;
- the public API cannot choose a model, prompt, provider URL, provider header, or generation parameter;
- the API calls a private LLM-Gateway connectivity-test route authenticated with Serviq's existing internal gateway token;
- the LLM Gateway owns the provider-to-test-model mapping and the fixed test request;
- the test performs exactly one non-streaming provider call;
- the test uses a fixed prompt, a four-token output ceiling, and a five-second provider timeout;
- success marks the connection `active`;
- credential authentication failure marks it `invalid`;
- transient or configuration-style provider failures preserve the previous persisted status and record only a stable error code;
- a disabled connection is not invoked and remains disabled;
- both frozen rate limits are enforced through shared Valkey state before the secret is resolved or any provider call is made;
- rate-limit infrastructure failure fails closed;
- the provider call happens outside every database transaction;
- a result is not written onto a credential that was rotated while the test was in flight.

## Public API contract

The public route remains exactly:

```text
POST /api/v1/providers/{providerConnectionId}/test
```

The route has no request body schema. A non-empty body is rejected. This matters because silently ignoring a caller-supplied body would make it unclear whether fields such as `model`, `prompt`, or `baseUrl` influence the request.

The route returns the normal Serviq success envelope with only the connectivity state needed by the caller:

```json
{
  "data": {
    "status": "active",
    "errorCode": null
  }
}
```

A provider-level failure is still a successfully executed connectivity test, so it uses the same safe result shape. For example, an invalid credential may return:

```json
{
  "data": {
    "status": "invalid",
    "errorCode": "PROVIDER_AUTH_FAILED"
  }
}
```

The response does not include:

- API keys;
- `secretRef`;
- upstream provider body text;
- provider SDK exception text;
- provider response headers;
- upstream request or response content;
- the selected upstream test model;
- the fixed test prompt;
- usage or billing metadata.

Authorization, tenant isolation, malformed requests, rate-limit enforcement, missing internal dependencies, and other API-control failures continue to use the normal Serviq HTTP error behavior rather than pretending that a provider test completed.

## Provider-management authorization and tenant isolation

The endpoint uses the existing permission:

```text
ai.providers.manage
```

The provider connection is looked up by both:

- the current tenant ID; and
- the requested provider-connection ID.

A provider connection owned by another tenant must not be distinguishable from a provider connection that does not exist. The existing provider service behavior therefore remains authoritative: cross-tenant/nonmember access is non-disclosing and maps to `PROVIDER_NOT_FOUND`.

The provider key is never accepted from the request and is never inferred from an arbitrary string. Adapter selection begins only from the stored provider enum.

## Private API-to-LLM-Gateway contract

OPE-298 may add one private, service-to-service route owned by the LLM Gateway:

```text
POST /internal/v1/provider-connectivity-test
```

This is not a tenant-facing or public C-4 endpoint. It exists only to keep provider adapter execution inside the LLM Gateway service.

The private request contains only server-resolved administrative context:

```json
{
  "tenantId": "uuid",
  "provider": "openai|anthropic|gemini|openrouter",
  "apiKey": "server-resolved secret",
  "correlationId": "server-generated value"
}
```

The model, prompt, timeout, output-token budget, provider URL, streaming flag, headers, and routing preferences are intentionally absent.

The route is authenticated with the existing Serviq platform setting:

```text
LLM_GATEWAY_INTERNAL_TOKEN
```

The bearer token comparison must be constant-time. Missing or incorrect internal authentication is rejected before a provider adapter is constructed or invoked.

The private route returns no generated provider content. It returns either a minimal success marker or one of the existing safe C-4 provider error codes.

Production deployment must protect API-to-gateway traffic using the platform's service-network/TLS controls. OPE-298 does not add a second tenant credential store to the LLM Gateway and does not persist the credential there.

## Server-owned test-model mapping

The LLM Gateway owns this mapping in code. The public API and tenant cannot override it:

| Stored provider | Connectivity-test upstream model |
|---|---|
| `openai` | `gpt-5-nano` |
| `anthropic` | `claude-haiku-4-5-20251001` |
| `gemini` | `gemini-3.5-flash-lite` |
| `openrouter` | `openrouter/free` |

The mapping is intentionally separate from tenant `model_configurations`. A provider connection must be testable before the tenant has created a model configuration, and a broken tenant model alias must not be confused with a broken provider credential.

The choices favor a small, low-cost/current provider-supported model path rather than a premium model. OpenRouter uses its documented zero-cost free-model router. Because free-model availability can vary, an OpenRouter transient failure does **not** invalidate an otherwise previously working credential.

Changing this mapping later is an architecture-owned operational change. It must not become a caller-controlled field.

## Fixed minimal provider request

The gateway constructs exactly one non-streaming C-4 request with:

- purpose: `classification`;
- one user message containing the fixed Serviq-owned text `Reply with OK.`;
- empty response schema;
- `maxOutputTokens = 4`;
- `timeoutMs = 5000`;
- `stream = false`;
- server-generated model alias/correlation metadata used only for tracing the test.

The generated text itself is irrelevant. Any successful normalized provider response proves that the credential, endpoint, adapter translation, and selected lightweight model path are reachable.

The implementation must not retry the connectivity call. Existing provider adapters already disable hidden SDK retries where their ADRs require Serviq to own retry behavior. An administrative test should report the observed result rather than hide it behind repeated paid calls.

## Persisted status semantics

Provider connection status describes credential usability, not general provider uptime.

### Success

On a successful provider call:

```text
status = active
last_tested_at = now
last_error_code = NULL
```

### Authentication failure

For:

```text
PROVIDER_AUTH_FAILED
```

persist:

```text
status = invalid
last_tested_at = now
last_error_code = PROVIDER_AUTH_FAILED
```

An explicit provider authentication/authorization failure is the only connectivity-test failure that changes a non-disabled connection to `invalid`.

### Transient provider failures

For:

```text
PROVIDER_RATE_LIMITED
PROVIDER_TIMEOUT
PROVIDER_UNAVAILABLE
```

preserve the existing status and persist:

```text
last_tested_at = now
last_error_code = <stable C-4 code>
```

Examples:

- an `active` connection stays `active` during a provider outage;
- an `untested` connection stays `untested` if its first attempt times out;
- an `invalid` connection stays `invalid` if a later retest cannot reach the provider.

This prevents a temporary upstream incident from being stored as false evidence that a credential is bad.

### Provider invalid-request failure

`PROVIDER_INVALID_REQUEST` also preserves the previous status and stores the stable error code.

For this endpoint the model and prompt are Serviq-owned. Therefore an invalid-request response may indicate that Serviq's selected health-check model or translation is no longer accepted by the provider. It is not safe evidence that the tenant credential itself is invalid.

### Disabled connection

A connection whose stored status is `disabled` is not invoked. It returns safe disabled state without resolving the credential or spending provider capacity.

OPE-298 does not add an enable/disable lifecycle API; it only respects the already frozen status.

## `last_tested_at` meaning

`last_tested_at` records the time of the latest provider connectivity attempt whose result was applied to the current credential.

It is updated for:

- success;
- provider authentication failure;
- provider rate limiting;
- provider timeout;
- provider unavailable;
- provider invalid request.

It is not updated when:

- authorization fails before testing;
- the provider ID belongs to another tenant or does not exist;
- the endpoint is rejected by Serviq's own rate limiter;
- the connection is disabled and therefore not invoked;
- the stored credential was rotated while the external call was in flight and the result is discarded as stale.

## Credential-rotation concurrency rule

The external provider call must not execute inside a database transaction, so the connection row cannot remain locked while waiting on the provider.

OPE-298 therefore uses a two-phase pattern:

1. authorize and read the tenant-scoped provider connection in a short database transaction;
2. capture the tested `secret_ref`, stored provider enum, and current status;
3. leave the transaction;
4. enforce rate limits;
5. resolve that captured secret and make the provider call;
6. open a new short database transaction and lock the provider row;
7. verify that the current row still has the same `secret_ref` and provider value;
8. only then persist the result.

If the key was rotated while the test was running, the old result is stale and must not overwrite the new key's `untested` metadata. The endpoint returns a stable Serviq conflict/retry error rather than guessing.

This also prevents a successful test of an old key from marking a newly rotated but untested key `active`.

## Rate-limit policy

The already frozen limits are:

```text
provider.test.user       = 10 / minute
provider.test.connection = 30 / hour
```

Both limits are checked before secret resolution and before the LLM Gateway/provider call.

Keys are scoped by tenant as well as the limiting subject:

- user key: tenant ID + workforce user ID;
- connection key: tenant ID + provider connection ID.

Enforcement uses shared Valkey state, not a Python process-local dictionary. A process-local limiter would reset on restart and allow each API worker to have a separate allowance, which would violate the meaning of the frozen limits once Serviq scales horizontally.

The implementation may use the recommended `valkey-py` client and an atomic server-side script/transaction so both limits are checked and consumed as one decision. The exact storage key is internal and must not contain secrets.

If Valkey/rate-limit enforcement is unavailable, the endpoint fails closed with a safe platform error and **does not** invoke the provider. Paid/external connectivity tests must never become unlimited because the abuse-control dependency failed.

The API's own rate-limit rejection is different from a provider's `PROVIDER_RATE_LIMITED` result:

- Serviq rate-limit rejection means the external call was not made and no provider metadata is changed;
- provider rate limiting means the call was attempted and `last_tested_at`/`last_error_code` are updated while status is preserved.

## Secret handling

The API resolves `secret_ref` only through `TenantSecretStore.get_secret(tenant_id, secret_ref)`.

The plaintext credential may exist only long enough to construct the authenticated private gateway request and provider adapter context. It must never be:

- persisted in PostgreSQL;
- returned to the browser/client;
- copied into `last_error_code`;
- placed in a URL/query string;
- included in structured application logs;
- interpolated into exception messages authored by OPE-298;
- included in tracing attributes.

The private gateway request body is also never logged by OPE-298.

## Safe error vocabulary

Provider connectivity outcomes use only the existing C-4 codes:

```text
PROVIDER_AUTH_FAILED
PROVIDER_RATE_LIMITED
PROVIDER_TIMEOUT
PROVIDER_UNAVAILABLE
PROVIDER_INVALID_REQUEST
```

The public API may additionally use Serviq-owned control-plane errors for conditions where no provider test result exists, including:

```text
PROVIDER_NOT_FOUND
FORBIDDEN
PROVIDER_TEST_RATE_LIMITED
PROVIDER_TEST_UNAVAILABLE
PROVIDER_TEST_STALE
```

Messages are fixed Serviq text. Raw provider or internal HTTP bodies are not propagated.

## Logging and observability

OPE-298 may log safe identifiers and categorical outcomes such as:

- tenant ID;
- provider connection ID;
- stored provider enum;
- correlation ID;
- stable outcome/error code;
- elapsed duration.

It must not log:

- API key;
- secret-store plaintext;
- `secret_ref` unless a later observability ADR explicitly approves it;
- fixed/private request body;
- provider response body;
- provider SDK exception text;
- generated model content.

## Testing requirements

CI tests for OPE-298 must not make live provider requests.

Required coverage includes:

- each stored provider selects only its frozen server-owned model;
- the private gateway test creates only the fixed one-message request;
- the public route rejects a non-empty arbitrary body;
- success persists `active`, timestamp, and clears error;
- auth failure persists `invalid` + `PROVIDER_AUTH_FAILED`;
- provider 429, timeout, unavailable, and invalid-request preserve previous status and store only stable codes;
- wrong-tenant provider IDs remain non-disclosing;
- users without `ai.providers.manage` are denied;
- user and connection rate limits prevent provider invocation;
- Valkey/rate-limiter failure prevents provider invocation;
- disabled provider connections are not invoked;
- credential rotation during an in-flight test prevents a stale result from being persisted;
- secret/raw provider error material is absent from API responses, database `last_error_code`, and captured logs;
- private gateway authentication is required;
- no provider SDK type crosses the private gateway/public API boundary.

Fake/mocked adapters and a fake injectable rate limiter are acceptable for deterministic route tests. The production rate-limit implementation itself must remain shared-state Valkey-backed.

## External documentation reviewed

Decision reviewed against current provider/client documentation on 2026-08-18:

- OpenAI model documentation for `gpt-5-nano`;
- Anthropic current model documentation for Claude Haiku 4.5 (`claude-haiku-4-5-20251001`);
- Google Gemini API documentation for stable `gemini-3.5-flash-lite`;
- OpenRouter Free Models Router documentation for `openrouter/free` and its availability/rate-limit tradeoffs;
- Valkey recommended client documentation for Python `valkey-py` and RESP-compatible shared state.

## Scope exclusions

OPE-298 does not approve or implement:

- caller-selected prompts;
- caller-selected upstream models;
- arbitrary provider/base URLs;
- model configuration CRUD;
- general C-4 HTTP routing for agent traffic;
- provider fallback chains;
- provider retries for connectivity tests;
- a new provider enum;
- a new provider SDK;
- provider-key lifecycle changes;
- agent runtime changes;
- paid health-check scheduling;
- background periodic provider monitoring.

## Result

OPE-298's architecture stop condition is resolved once this ADR is merged. Runtime implementation may proceed with a fixed, bounded, tenant-safe connectivity test without inventing status semantics or exposing a new free-form model proxy.