# OPE-298 — Provider connectivity-test architecture blockers

## Status

**Resolved by ADR-014.** This file is retained as an audit trail explaining why the first OPE-298 implementation attempt correctly stopped, what was missing, and what later changed before implementation resumed.

The authoritative decision is now:

- `docs/architecture-decisions/ADR-014-provider-connectivity-test-semantics.md`

ADR-014 was merged before the runtime implementation branch was created.

## What OPE-298 builds

OPE-298 implements a safe administrative health check for a stored Bring Your Own Key (BYOK) provider connection:

```text
POST /api/v1/providers/{providerConnectionId}/test
```

A tenant administrator can ask Serviq, in effect, "Can the provider credential I already saved make one tiny model request?"

The endpoint must not become a general model-completion proxy. The browser cannot supply a prompt, model, provider URL, header, timeout, token budget, or other model-generation controls. Serviq creates one fixed minimal request, resolves the saved tenant-scoped credential, invokes the correct adapter through the LLM Gateway, stores only safe provider-health metadata, and returns only normalized status/error information.

## Why the first attempt stopped

The original ticket deliberately contained a `Needs Architect Decision` stop condition. At that time, three categories of required behavior were not sufficiently frozen.

### 1. Minimal model-selection strategy was missing

The public architecture had not said which upstream model Serviq should use for each provider or whether a tenant needed to create a model configuration before a provider credential could be tested.

Inventing a model choice inside feature code would have created a hidden product contract. It would also have made it unclear whether a failed test meant "the API key is bad" or merely "the model string chosen by this implementation is bad."

### 2. Transient-failure status semantics were missing

The provider table already allowed these states:

- `untested`;
- `active`;
- `invalid`;
- `disabled`.

But the architecture had not defined what a temporary upstream rate limit, timeout, outage, or provider-side bad request should do to the persisted status. Marking a credential `invalid` for every failure would be incorrect because an upstream outage does not prove that the tenant's credential is wrong.

### 3. Provider coverage was incomplete

At the time the blocker was written, Gemini and OpenRouter adapters were still awaiting their own architecture decisions. OPE-298 is a four-provider feature, so implementing a health check for only OpenAI and Anthropic would have produced inconsistent behavior.

## What changed before implementation resumed

The prerequisites were completed in order:

1. Gemini received its frozen SDK/adapter baseline and implementation.
2. OpenRouter received its frozen transport/adapter baseline and implementation.
3. All four stored provider enum values therefore had C-4 adapters on `main`.
4. ADR-014 froze the remaining connectivity-test behavior.

Only after these conditions were true was OPE-298 moved back into active implementation.

## Decisions frozen by ADR-014

### Public request shape

The route remains exactly:

```text
POST /api/v1/providers/{providerConnectionId}/test
```

The public route accepts no body. A non-empty body is rejected instead of ignored. This makes it impossible for a caller to believe that fields such as `model`, `prompt`, or `baseUrl` influence the request.

### Server-owned test models

The LLM Gateway owns the provider-to-test-model mapping. The tenant/browser cannot override it:

| Provider | Server-owned connectivity-test model |
|---|---|
| OpenAI | `gpt-5-nano` |
| Anthropic | `claude-haiku-4-5-20251001` |
| Gemini | `gemini-3.5-flash-lite` |
| OpenRouter | `openrouter/free` |

The mapping is intentionally independent of tenant model configurations. A tenant must be able to test a provider credential before creating model aliases.

### Fixed bounded request

Every test uses one Serviq-owned request:

- prompt: `Reply with OK.`;
- one user message;
- non-streaming;
- maximum output: 4 tokens;
- provider timeout: 5 seconds;
- no caller response schema;
- no retry loop.

The generated text is discarded. A successful normalized provider response is enough to prove connectivity.

### Status semantics

On success:

- `status = active`;
- `last_tested_at = now`;
- `last_error_code = NULL`.

On `PROVIDER_AUTH_FAILED`:

- `status = invalid`;
- `last_tested_at = now`;
- `last_error_code = PROVIDER_AUTH_FAILED`.

On provider rate limit, timeout, unavailable, or invalid-request failures:

- preserve the current status;
- update `last_tested_at`;
- store only the stable normalized C-4 error code.

A temporary provider problem therefore cannot falsely prove that a tenant credential is invalid.

A connection already marked `disabled` is not invoked.

### API-to-gateway boundary

The API does not import provider SDKs or execute adapters directly. It sends a narrow authenticated request to:

```text
POST /internal/v1/provider-connectivity-test
```

The private request contains only server-resolved administrative context:

- tenant ID;
- stored provider enum;
- resolved API key;
- correlation ID.

It does not contain caller-selected generation controls.

The private route uses the existing `LLM_GATEWAY_INTERNAL_TOKEN` service credential, and the gateway compares bearer-token values in constant time.

### Shared rate limiting

The previously frozen limits remain authoritative:

```text
provider.test.user       = 10 / minute
provider.test.connection = 30 / hour
```

The production implementation uses shared Valkey state rather than an in-process Python dictionary. This matters because separate API workers must see the same counters.

Both limits are checked and consumed atomically by one Valkey script. If the rate-limit store is unavailable or returns malformed data, provider testing fails closed and no provider call is made.

### Credential-rotation race protection

A provider call must not hold a PostgreSQL transaction open while waiting on the network. The implementation therefore uses two short database transactions:

1. authorize, read the provider row, and capture its `secret_ref` and provider enum;
2. leave the transaction and perform rate limiting, secret resolution, and the external gateway/provider call;
3. open a new transaction, lock the row, and verify that the credential reference still matches what was tested;
4. persist the result only when the tested credential is still current.

If a key is rotated while the test is running, the old result is rejected as stale. This prevents an old successful key from marking a newly rotated but untested key `active`.

## Stable control-plane errors added

OPE-298 uses the existing normalized provider codes for provider outcomes:

- `PROVIDER_AUTH_FAILED`;
- `PROVIDER_RATE_LIMITED`;
- `PROVIDER_TIMEOUT`;
- `PROVIDER_UNAVAILABLE`;
- `PROVIDER_INVALID_REQUEST`.

For failures where no valid provider-test result exists, the API may return safe Serviq control-plane codes including:

- `PROVIDER_NOT_FOUND`;
- `FORBIDDEN`;
- `PROVIDER_TEST_RATE_LIMITED`;
- `PROVIDER_TEST_UNAVAILABLE`;
- `PROVIDER_TEST_STALE`.

Raw provider response bodies, SDK exception text, API keys, and secret references are not copied into these fields.

## Why resolving the blocker this way improves the product

The endpoint now has a precise answer to each ambiguity that originally made implementation unsafe:

- model selection belongs to Serviq, not the caller;
- a health check does not depend on tenant model aliases;
- temporary upstream incidents do not corrupt credential state;
- all four supported providers use the same public behavior;
- provider SDK execution remains inside the LLM Gateway;
- rate limiting works across horizontally scaled API workers;
- provider calls do not hold database locks;
- rotating a credential cannot be overwritten by an old in-flight test result;
- raw provider details and credentials remain outside browser-safe metadata.

The original stop was therefore not discarded or bypassed. It did its job: implementation resumed only after the missing architecture was explicitly frozen and merged.
