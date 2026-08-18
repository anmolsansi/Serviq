# OPE-298 — Provider Connectivity Test: What We Built, How It Works, and Why

## Who this document is for

This document is written so that a new intern, a nontechnical teammate, a customer-operations person, or a high-school student can understand what OPE-298 changed without first learning the whole Serviq codebase.

The short version is:

> OPE-298 gives an authorized tenant administrator a safe **Test connection** action for an AI provider API key that is already stored in Serviq.

For example, imagine a company connects its OpenAI account to Serviq. The company pastes its OpenAI API key into the provider settings screen. Before trusting that connection for real customer-support work, the administrator wants Serviq to answer a simple question:

> "Does this saved key actually work?"

OPE-298 implements the backend behavior required to answer that question safely.

It does **not** let the administrator type arbitrary prompts, choose expensive models, change provider URLs, or use the endpoint as another chat API. It performs one tiny, controlled health check and stores a safe result.

---

# 1. The problem before OPE-298

Serviq already had provider-connection records. A provider connection stores information such as:

- which AI company it belongs to, such as OpenAI, Anthropic, Gemini, or OpenRouter;
- a display name chosen by the tenant;
- a reference to the safely stored API key;
- a status such as `untested`, `active`, `invalid`, or `disabled`;
- when the connection was last tested;
- a safe error code from the last test.

The important word above is **reference**.

Serviq does not intentionally store the plaintext API key in the normal provider row in PostgreSQL. The row points to the tenant secret store, where the sensitive value is stored separately.

Before OPE-298, an administrator could create or update provider connection metadata, but there was no production-ready endpoint that safely performed the actual health check and updated that metadata.

A naive implementation would be easy to write but dangerous. For example:

1. receive a provider ID;
2. read the API key;
3. ask the caller which model/prompt to use;
4. call the provider;
5. if anything fails, mark the key invalid.

That looks simple, but it creates several serious problems.

### Problem A: the health endpoint becomes a hidden chat/completion endpoint

If the user can choose a prompt or model, the endpoint is no longer just a connection test. Someone could repeatedly use it to make arbitrary AI requests.

### Problem B: temporary outages look like bad API keys

A timeout or provider outage does not mean the key is invalid. If every error changed the status to `invalid`, Serviq would show false information.

### Problem C: repeated tests can create cost/abuse

Even tiny AI requests use external provider capacity. Without shared rate limiting, one user or many API workers could generate too many tests.

### Problem D: a key can be rotated while the test is running

Suppose key A is being tested. While that request is waiting on OpenAI, another administrator replaces the key with key B. If the old request succeeds and Serviq blindly writes `active`, the database now says key B is active even though key B was never tested.

### Problem E: holding a database transaction open during an AI call is dangerous

Provider calls can take seconds or time out. Holding a database transaction or row lock open for that whole time hurts concurrency and reliability.

### Problem F: provider error text can leak secrets or private details

Raw provider bodies and SDK exception messages are not safe database/UI contracts. They can contain request fragments or provider-specific information.

OPE-298 was designed to solve all of these together rather than adding a superficial button endpoint.

---

# 2. Why the implementation originally stopped

The first OPE-298 repository audit found that the public route and rate-limit numbers were already documented, but two important product rules were missing:

1. which small model Serviq should use for each provider;
2. what persistent status should do when the provider fails temporarily.

At that time, Gemini and OpenRouter adapters were also not complete.

The ticket explicitly said to stop when architecture decisions were missing, so implementation correctly stopped rather than inventing hidden rules.

Later:

- the Gemini adapter was completed;
- the OpenRouter adapter was completed;
- ADR-014 was written and merged.

ADR means **Architecture Decision Record**. It is a document that records a technical/product rule so future code does not have to guess what the system is supposed to do.

ADR-014 froze the missing provider-test behavior. Only then did the runtime implementation begin.

The historical blocker file remains in the repository, but its status is now marked resolved.

---

# 3. What endpoint was implemented

The public endpoint is:

```text
POST /api/v1/providers/{providerConnectionId}/test
```

Example idea:

```text
POST /api/v1/providers/8b54.../test
```

The caller supplies only the provider-connection ID in the URL.

There is intentionally **no request body**.

If somebody sends a body like:

```json
{
  "model": "some-expensive-model",
  "prompt": "write me an essay",
  "baseUrl": "https://some-other-server.example"
}
```

Serviq rejects it.

This is not just strict validation for neatness. It is a security/product boundary. A connection test must remain a connection test.

---

# 4. Who is allowed to use it

The route uses Serviq's existing provider-management permission:

```text
ai.providers.manage
```

That means the current workforce user must:

1. belong to the active tenant context;
2. have the provider-management permission;
3. request a provider connection that belongs to that same tenant.

If a provider ID belongs to another tenant, Serviq does not reveal that fact. The result behaves like "provider not found."

Why?

Because returning something like:

> "This provider exists, but it belongs to tenant B"

would disclose cross-tenant information.

The integration tests create two real tenants in PostgreSQL to verify this behavior.

---

# 5. The test is server-controlled, not user-controlled

The LLM Gateway owns a fixed provider-to-test-model mapping:

| Provider | Connectivity-test model |
|---|---|
| OpenAI | `gpt-5-nano` |
| Anthropic | `claude-haiku-4-5-20251001` |
| Gemini | `gemini-3.5-flash-lite` |
| OpenRouter | `openrouter/free` |

The browser does not choose these names.

The tenant's future model aliases also do not choose them.

Why keep health-check models separate from normal model configuration?

Because an administrator often wants to test the provider **before** configuring application models. A broken model alias should also not be confused with a broken provider credential.

If one of these provider model identifiers needs to change later, that should be an explicit architecture/operations change, not a hidden field exposed to the caller.

---

# 6. The exact small request Serviq creates

The gateway constructs one provider-neutral C-4 request.

C-4 is Serviq's internal provider-neutral language-model contract. "Provider-neutral" means the rest of Serviq can express one common request without knowing OpenAI's SDK shapes, Anthropic's SDK shapes, Gemini's SDK shapes, and so on.

The connectivity request is deliberately tiny:

```text
Prompt: Reply with OK.
Maximum output: 4 tokens
Timeout: 5 seconds
Streaming: no
Retries added by OPE-298: none
```

A **token** is a small chunk of text used by language models. Four output tokens are enough for a tiny connectivity response and keep the health check bounded.

Serviq does not care whether the provider literally returns `OK`. The important fact is that the provider accepted the authenticated request and returned a successful normalized response.

The generated content is discarded.

The public browser response does not receive:

- generated text;
- token usage;
- provider request ID;
- model output;
- raw provider headers;
- raw provider response body.

This keeps the endpoint focused on health, not inference.

---

# 7. Why there is a private LLM-Gateway endpoint

The public API service should not contain OpenAI/Anthropic/Gemini/OpenRouter SDK logic. Serviq already has a dedicated LLM Gateway for provider adapters.

Therefore the API calls a narrow internal route:

```text
POST /internal/v1/provider-connectivity-test
```

This is a service-to-service route, not a tenant-facing feature endpoint.

Its request contains only:

```json
{
  "tenantId": "...",
  "provider": "openai",
  "apiKey": "server-resolved-key",
  "correlationId": "server-generated-id"
}
```

Notice what is missing:

- model;
- prompt;
- base URL;
- timeout;
- max token count;
- streaming flag;
- arbitrary headers.

Those values remain owned by the gateway implementation.

The private route requires the existing internal bearer token:

```text
LLM_GATEWAY_INTERNAL_TOKEN
```

The gateway compares the supplied and expected internal tokens using a constant-time comparison (`hmac.compare_digest`).

A **constant-time comparison** is designed to avoid revealing useful timing differences based on how many characters of a secret were correct.

Production deployment must still protect this internal service traffic with the normal private-network/TLS controls because the provider API key necessarily travels from the API process to the LLM Gateway process in order to call the provider.

---

# 8. Where the API key comes from

The public `/test` request never accepts an API key.

Instead, Serviq reads the provider row, gets its `secret_ref`, and asks the tenant secret store for the corresponding secret.

Conceptually:

```text
Browser
  |
  | POST /providers/<id>/test
  v
Serviq API
  |
  | lookup provider row for this tenant
  v
provider_connections
  |
  | secret_ref (not plaintext key)
  v
Tenant Secret Store
  |
  | plaintext key only in server memory
  v
Private LLM Gateway request
```

This prevents the connectivity route from becoming another key-ingestion path.

If the secret cannot be resolved safely, Serviq returns a controlled `PROVIDER_TEST_UNAVAILABLE` result rather than exposing secret-store errors.

---

# 9. Rate limiting: why we added Valkey

The architecture already froze two limits:

```text
10 tests per minute per tenant user
30 tests per hour per provider connection
```

These limits answer two different abuse questions.

### User limit

One person should not be able to hammer many provider tests continuously.

### Connection limit

A specific provider connection should not be tested too many times even if multiple authorized administrators are clicking the button.

A simple Python dictionary would not be production-safe.

Imagine Serviq runs three API processes:

```text
API worker 1 -> local count 8
API worker 2 -> local count 7
API worker 3 -> local count 9
```

Each process believes the user is under 10, while the real combined count is already 24.

OPE-298 therefore uses **Valkey**, the shared in-memory datastore already present in Serviq's architecture.

The API adds the official Python Valkey client dependency and refreshes its frozen lock file. Repository CI resolved `valkey==6.1.1` for the current API environment.

---

# 10. The two limits are checked atomically

"Atomic" means the important operation behaves like one indivisible action from the perspective of concurrent workers.

OPE-298 sends one Valkey script that:

1. reads the user counter;
2. reads the provider-connection counter;
3. rejects when either is exhausted;
4. otherwise increments both;
5. gives new counters their correct expiration windows;
6. returns a retry-after value when blocked.

This avoids a classic race:

```text
Worker A reads count 9
Worker B reads count 9
Worker A decides "allowed"
Worker B decides "allowed"
Both increment
```

With separate read/check/write operations, both workers can incorrectly pass the same remaining slot.

The shared atomic script prevents that problem.

---

# 11. What happens if Valkey itself is down

Serviq deliberately **fails closed**.

Fail closed means:

> If the system cannot prove the request is allowed, it does not perform the external provider call.

So if Valkey is unavailable or returns malformed data:

```text
PROVIDER_TEST_UNAVAILABLE
```

is returned and the provider is not invoked.

Why not fail open?

Because failing open would turn a rate-limited external-cost endpoint into an unlimited one exactly when the protection system is broken.

---

# 12. How provider status changes

This is one of the most important product decisions in OPE-298.

## Successful test

A successful provider call means the current credential successfully authenticated and reached the selected health-check model.

Serviq stores:

```text
status = active
last_tested_at = now
last_error_code = null
```

## Authentication failure

If the provider explicitly says authentication/authorization failed:

```text
PROVIDER_AUTH_FAILED
```

Serviq stores:

```text
status = invalid
last_tested_at = now
last_error_code = PROVIDER_AUTH_FAILED
```

This is direct evidence that the tested credential cannot authenticate for the test request.

## Provider rate limit

If the external provider says:

```text
PROVIDER_RATE_LIMITED
```

Serviq updates the timestamp/error code but **preserves the current status**.

A rate limit does not prove the API key is wrong.

## Timeout

For:

```text
PROVIDER_TIMEOUT
```

Serviq preserves current status and records the attempt.

## Provider unavailable

For:

```text
PROVIDER_UNAVAILABLE
```

Serviq preserves current status and records the attempt.

## Provider invalid request

For:

```text
PROVIDER_INVALID_REQUEST
```

Serviq also preserves current status.

Why?

Because the health-check model/prompt are Serviq-owned. If a provider retires the selected test model tomorrow, the request might become invalid even though the tenant's API key is still perfectly valid. Marking the credential invalid would blame the customer for a Serviq/provider-contract problem.

---

# 13. Disabled providers are not tested

If the provider connection is already:

```text
disabled
```

Serviq does not:

- consume a rate-limit slot;
- resolve the secret;
- call LLM Gateway;
- call the provider;
- reactivate the connection.

It returns the safe disabled state.

This prevents a health-check action from silently overriding an administrative disable decision.

---

# 14. The two-transaction design

This is the most important reliability/concurrency detail in the implementation.

The provider call happens **outside** a database transaction.

The flow is:

```text
Transaction A
  - authorize user
  - find tenant-scoped provider
  - capture provider enum + secret_ref
Commit/close transaction

Outside database transaction
  - enforce Valkey rate limits
  - resolve credential from secret store
  - call private LLM Gateway/provider

Transaction B
  - lock provider row
  - verify provider + secret_ref are still the same
  - store safe result
Commit
```

Why not keep one transaction open?

Because external provider latency is unpredictable. A five-second timeout is a very long time for a database row lock when many users and services need the same database.

Separating the network call keeps database transactions short.

---

# 15. The credential-rotation race and how we fixed it

Imagine this timeline:

```text
10:00:00  Test begins using key A
10:00:01  Admin rotates provider to key B
10:00:02  OpenAI says key A worked
10:00:02  Old test tries to write "active"
```

Without protection, key B could now appear `active` despite never being tested.

OPE-298 captures the original `secret_ref` before the external call.

When the call finishes, it locks the provider row and asks:

```text
Does the row still point to the same secret_ref and provider that I tested?
```

If yes, the result is still valid and can be stored.

If no, Serviq returns:

```text
PROVIDER_TEST_STALE
```

and does **not** apply the old result.

The PostgreSQL integration test simulates exactly this race by rotating the credential in a separate database session while the fake provider call is in flight.

It verifies that the replacement key remains:

```text
status = untested
last_tested_at = null
last_error_code = null
```

This is an example of why production-ready behavior requires more than checking whether a happy-path HTTP request returns 200.

---

# 16. Safe error vocabulary

Serviq does not return raw provider exceptions to the browser.

Provider outcomes use the existing C-4 categories:

```text
PROVIDER_AUTH_FAILED
PROVIDER_RATE_LIMITED
PROVIDER_TIMEOUT
PROVIDER_UNAVAILABLE
PROVIDER_INVALID_REQUEST
```

Serviq's own control-plane failures include:

```text
PROVIDER_NOT_FOUND
FORBIDDEN
PROVIDER_TEST_RATE_LIMITED
PROVIDER_TEST_UNAVAILABLE
PROVIDER_TEST_STALE
```

A **control plane** is the administrative/configuration side of a system. Here it means failures in Serviq's own process of authorizing, rate-limiting, locating, and safely applying the connectivity test—not failures returned by the AI provider itself.

Keeping these two ideas separate makes debugging and UI messaging much clearer.

---

# 17. Files added or changed

## Architecture

### `docs/architecture-decisions/ADR-014-provider-connectivity-test-semantics.md`

Freezes the previously missing product/technical rules before runtime code is allowed to depend on them.

### `docs/architecture-blockers/OPE-298-provider-test-contract-decisions.md`

Retains the history of the original stop condition and now explains how ADR-014 resolved it.

---

## LLM Gateway

### `services/llm-gateway/app/connectivity.py`

Implements the private health-check control path.

Responsibilities:

- private request/response schemas;
- internal bearer-token authentication;
- constant-time token comparison;
- server-owned model mapping;
- fixed C-4 test request;
- provider-adapter selection;
- normalized result with generated content discarded.

### `services/llm-gateway/app/main.py`

Registers the private connectivity router with the FastAPI gateway application.

### `services/llm-gateway/tests/test_provider_connectivity.py`

Verifies:

- all provider model mappings;
- fixed prompt/budget;
- no arbitrary private controls;
- internal authentication;
- generated content/request ID/secret not returned;
- normalized provider failure behavior.

---

## API service

### `services/api/app/modules/providers/gateway.py`

Implements the narrow API-to-LLM-Gateway HTTP client.

It knows only the fixed internal route and safe response shape.

It does not parse or return raw error bodies.

### `services/api/app/core/rate_limits.py`

Implements the shared Valkey provider-test limiter.

Responsibilities:

- tenant/user key;
- tenant/provider-connection key;
- atomic script;
- retry-after result;
- fail-closed Valkey error handling;
- cached async Valkey client.

### `services/api/app/modules/providers/service.py`

Implements the actual business process:

- authorization;
- first short transaction;
- disabled short-circuit;
- rate limit;
- secret resolution;
- gateway call outside transaction;
- second locked transaction;
- stale credential check;
- correct status/error persistence.

### `services/api/app/modules/providers/router.py`

Adds the public route and HTTP-level error mappings.

It also rejects any non-empty request body.

### `services/api/app/modules/providers/schemas.py`

Adds the small browser-safe connectivity result schema and normalized provider error type.

### `services/api/app/modules/providers/errors.py`

Adds stable control exceptions for:

- rate-limited test;
- unavailable test infrastructure;
- stale test result.

### `services/api/pyproject.toml`

Adds the Valkey Python client runtime dependency.

### `services/api/uv.lock`

Refreshes the frozen API dependency graph so CI/deployments install the same resolved dependency version instead of resolving a different package later.

---

## Tests

### `services/api/tests/integration/test_provider_connectivity_api.py`

Uses the real PostgreSQL integration environment and verifies the public business flow.

### `services/api/tests/test_provider_connectivity_gateway.py`

Uses `httpx.MockTransport` to test the production internal HTTP boundary without a real LLM Gateway network call.

### `services/api/tests/test_provider_test_rate_limits.py`

Tests the production rate-limit logic using a fake Valkey eval client without requiring live Valkey in the CI integration job.

---

## Security documentation

### `docs/security-reviews/OPE-298-provider-connectivity-test.md`

Contains the detailed adversarial review of:

- arbitrary proxy risk;
- SSRF risk;
- BYOK leakage;
- tenant/RBAC isolation;
- abuse/cost amplification;
- transient status corruption;
- key-rotation races;
- database transaction duration;
- raw error leakage;
- retries;
- disabled state;
- internal auth;
- CI/live-network behavior;
- dependency/supply-chain scope.

---

# 18. What the tests cover

OPE-298 does not rely only on one happy-path unit test.

## Gateway tests

They verify:

- OpenAI gets only its frozen test model;
- Anthropic gets only its frozen test model;
- Gemini gets only its frozen test model;
- OpenRouter gets only its frozen test model;
- the fixed prompt is used;
- output budget is 4;
- timeout is 5,000 ms;
- streaming is false;
- private auth is required;
- private extra fields are rejected;
- generated model content never crosses the connectivity response.

## Internal HTTP client tests

They verify:

- exact fixed internal path;
- internal Authorization header;
- payload contains only tenant/provider/key/correlation ID;
- no model/prompt/baseUrl field;
- raw 500 response bodies are discarded;
- raw secrets in those bodies are not propagated;
- timeout becomes only `PROVIDER_TIMEOUT`;
- timeout causes exactly one internal HTTP attempt.

## Valkey tests

They verify:

- one atomic script handles both counters;
- user limit is 10;
- connection limit is 30;
- windows are 60 and 3,600 seconds;
- keys are tenant-scoped;
- no secret enters the keys;
- denial preserves retry-after;
- connection errors fail closed;
- malformed results fail closed.

## PostgreSQL integration test

It verifies:

- success -> `active`;
- auth failure -> `invalid`;
- provider 429 keeps previous status;
- timeout keeps previous status;
- unavailable keeps previous status;
- provider invalid-request keeps previous status;
- timestamps/error codes persist safely;
- arbitrary public body is rejected before provider invocation;
- Serviq rate limit prevents provider invocation;
- rate-limit infrastructure failure prevents provider invocation;
- disabled connection is not invoked;
- key rotation during an in-flight test creates a stale conflict and does not stamp the new key;
- cross-tenant provider ID returns non-disclosing not-found;
- same-tenant user without permission gets forbidden;
- fake plaintext key is not present in the encrypted secret-store file, captured logs, or public response.

---

# 19. What OPE-298 deliberately does not build

Production scope is easier to understand when exclusions are explicit.

OPE-298 does **not** implement:

- arbitrary user prompts;
- a general chat/completion endpoint;
- user-selected health-check models;
- arbitrary provider URLs;
- model configuration CRUD;
- automatic fallback between providers;
- scheduled provider health monitoring;
- background periodic tests;
- a new provider SDK;
- agent runtime model selection;
- general C-4 HTTP routing for all agent traffic;
- a provider enable/disable lifecycle UI;
- model-reference semantics for published agents.

Those are separate product/architecture concerns.

---

# 20. How this improves Serviq for a real client

Before this ticket, a tenant could save provider information but the system did not yet have the full production-safe backend behavior needed for a reliable **Test connection** action.

After OPE-298, Serviq can give an authorized administrator a bounded answer without exposing provider internals.

From a client's perspective, this improves onboarding and operations:

1. **Safer setup** — the admin can verify a saved provider credential before relying on it for customer work.
2. **Clearer status** — an upstream outage does not misleadingly tell the admin that their key is invalid.
3. **Better security** — the browser never sends the stored key back into the test request.
4. **Cost control** — the health check is tiny and rate limited.
5. **Multi-tenant safety** — one company cannot test or discover another company's provider connection.
6. **Concurrency safety** — rotating a key while a test is running cannot produce false `active` status.
7. **Operational safety** — provider latency does not keep database transactions open.
8. **Provider neutrality** — OpenAI, Anthropic, Gemini, and OpenRouter follow the same public workflow.
9. **Debuggability** — safe normalized errors tell the UI whether the problem is credentials, provider availability, provider rate limiting, or Serviq's own test infrastructure.

---

# 21. A simple mental model

A nontechnical way to think about the endpoint is a credit-card terminal test.

An administrator is not being given the ability to charge any amount to any card. They are pressing a controlled **Check terminal** button.

Serviq decides:

- what tiny test to run;
- where to send it;
- how often it may be run;
- how long it may take;
- which errors mean the credential is bad;
- which errors only mean the external service is temporarily unhealthy.

It then stores only the safe health result.

That is the design philosophy of OPE-298.

---

# 22. Completion criteria

OPE-298 is considered complete only when all of the following are true:

- ADR-014 is merged;
- runtime endpoint is implemented;
- all four provider adapters are reachable through the server-owned test mapping;
- public body cannot control generation;
- shared user/connection rate limits are implemented;
- provider calls happen outside DB transactions;
- stale credential results are rejected;
- correct success/auth/transient persistence semantics are tested;
- tenant/RBAC rules are tested;
- raw secret/provider error leakage tests are present;
- dependency lock is updated;
- premium security review is present;
- this implementation document is present;
- `docs/SERVIQ_BUILD_GUIDE.md` includes the cumulative OPE-298 explanation;
- final PR CI passes;
- final PR Security passes;
- runtime PR is merged;
- GitHub issue #129 is closed as completed;
- Linear OPE-298 is moved to Done.

The ticket must not be marked complete before the final validation and merge steps are actually finished.
