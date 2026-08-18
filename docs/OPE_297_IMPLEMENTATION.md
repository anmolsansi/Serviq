# OPE-297 — OpenRouter generation and streaming adapter implementation

## Who this document is for

This document explains OPE-297 in plain language. It is written so that a non-technical teammate, a new intern, or a high-school student can understand what was built, why the work was split into architecture and implementation, what security risks were considered, and how we test the result.

Technical terms are explained as they appear.

---

## 1. What problem OPE-297 solves

Serviq is designed to work with multiple AI providers without forcing the rest of the application to learn each provider's API.

The shared Serviq interface is called **Contract C-4**.

Think of C-4 as a common language. Product and agent code speak C-4. Small provider adapters translate between C-4 and a provider such as OpenAI, Anthropic, Gemini, or OpenRouter.

OPE-297 adds that translation layer for OpenRouter.

OpenRouter is useful because one OpenRouter account can access models from many underlying AI companies. That flexibility also creates a risk: if Serviq allowed callers to choose arbitrary URLs, arbitrary fallback rules, or arbitrary provider-routing options, the OpenRouter adapter could become much more powerful than the rest of the gateway contract intends.

OPE-297 therefore focuses on a narrow, controlled feature:

> Send a validated Serviq C-4 generation request to the fixed OpenRouter API using a saved tenant OpenRouter key and an already validated upstream model, then translate the result back into C-4.

---

## 2. Why the first OPE-297 attempt stopped

The original OPE-297 investigation found that the repository had not decided which OpenRouter client or HTTP transport was approved.

Several choices were technically possible:

- use OpenRouter's own Python SDK;
- use raw HTTP;
- reuse the OpenAI SDK against OpenRouter's OpenAI-compatible API;
- add another compatibility library.

Choosing one inside the feature ticket would have silently answered architecture and security questions such as:

- Who owns the OpenRouter base URL?
- Can a tenant change that URL?
- Which dependency version is production-approved?
- Who owns retry behavior?
- Which OpenRouter-specific headers are allowed?
- How do provider failures map into C-4?
- Does upgrading one SDK affect more than one provider adapter?

The ticket explicitly said to stop when that choice was not already frozen, so the earlier branch correctly created a blocker record instead of guessing.

---

## 3. How the blocker was resolved

A separate architecture decision was created:

`docs/architecture-decisions/ADR-013-openrouter-transport-baseline.md`

It was merged through GitHub PR #141 after the repository's CI and Security workflows passed.

ADR-013 decides that Serviq will use the already pinned:

`openai==2.53.0`

as the OpenRouter transport.

This may sound strange at first. Why use the OpenAI SDK for OpenRouter?

OpenRouter officially provides an OpenAI-compatible API and documents using the OpenAI SDK with the OpenRouter API base URL. Serviq already has the OpenAI SDK pinned, tested, and security-reviewed, so reusing the transport avoids adding another dependency only to send the same Chat Completions request shape.

The important part is that Serviq **does not reuse the OpenAI provider adapter itself**. OpenRouter gets its own adapter because:

- its provider identity is different;
- its endpoint is different;
- its API key is different;
- it can return provider errors in a special in-band format;
- its future provider-specific behavior must remain isolated;
- errors should say OpenRouter, not OpenAI.

---

## 4. The fixed OpenRouter destination

The OpenRouter adapter defines one code-owned base URL:

`https://openrouter.ai/api/v1`

This is one of the most important design decisions in the ticket.

A user can choose:

- which saved OpenRouter provider connection to use;
- which validated Serviq model configuration to use.

A user cannot choose:

- `https://another-api.example`;
- an internal server address;
- a cloud metadata address;
- a custom proxy endpoint;
- a different OpenRouter-compatible server.

Why does this matter?

If a public API accepted an arbitrary destination URL and then sent authenticated server-side requests to that destination, an attacker could potentially use the server as a network proxy. A class of security problems like this is often called **SSRF**, which stands for **Server-Side Request Forgery**.

OPE-297 prevents that by owning the destination in code.

The C-4 request model also rejects unknown fields, so values such as `baseUrl` and `endpoint` are not silently accepted.

The test suite deliberately tries to submit an attacker-controlled web URL and a link-local metadata-style URL through C-4 and verifies the request is invalid.

---

## 5. How the API key is handled

Serviq uses a BYOK model.

**BYOK** means **Bring Your Own Key**: a tenant provides its own provider API credential instead of Serviq sharing one global key across every customer.

OPE-297 does not create a new secret-storage system.

The OpenRouter adapter receives only a previously resolved `SecretStr` through `AdapterContext`.

That means the adapter does not read the key from:

- the customer's prompt;
- C-4 request JSON;
- query parameters;
- model configuration;
- a random environment variable.

The adapter unwraps the secret only when it creates the request-scoped provider client.

If the key is missing or blank, the request stops with the normalized C-4 authentication error before a provider request is attempted.

---

## 6. How the model is selected

C-4 does not let the provider adapter choose an arbitrary raw model string supplied by the caller.

The request carries a Serviq model alias. Higher-level Serviq code resolves that alias to a validated model configuration and then gives the adapter:

`context.upstream_model`

The OpenRouter adapter sends that string exactly as received from the validated context.

For example, the value could look conceptually like:

`anthropic/some-approved-model`

The adapter does not:

- scan the user's prompt for a model name;
- accept another `model` field from request JSON;
- append OpenRouter-specific variants;
- automatically choose a cheaper model;
- add a fallback model list;
- switch provider based on a user instruction.

This keeps model governance above the adapter instead of allowing a provider-specific module to bypass Serviq's model configuration rules.

---

## 7. Why OpenRouter has its own adapter instead of aliasing OpenAI

Both OpenAI and OpenRouter use an OpenAI-compatible Chat Completions request shape in this implementation, but they are not the same provider.

If Serviq simply reused `OpenAIAdapter`, several things would become confusing or wrong:

- normalized provider identity could be `openai` instead of `openrouter`;
- errors could say OpenAI when the failing service was OpenRouter;
- OpenRouter's in-band provider errors could be missed;
- the fixed endpoint distinction could be hidden;
- future OpenRouter-specific changes could accidentally alter OpenAI behavior.

So OPE-297 creates:

`services/llm-gateway/app/adapters/openrouter.py`

and exports:

`OpenRouterAdapter`

The code can reuse the same transport library while keeping the product/provider boundary separate.

---

## 8. Non-stream generation

A normal, non-stream request waits for the provider to finish before returning a response.

The adapter translates C-4 into the OpenAI-compatible Chat Completions request using:

- the validated upstream model;
- C-4 messages in their existing order;
- the C-4 maximum output-token budget;
- the C-4 timeout budget;
- optional C-4 JSON Schema structured-output settings.

The adapter then translates the provider result into Serviq fields:

- `content`;
- `structured`;
- `provider = openrouter`;
- `upstreamModel`;
- input/output token usage;
- finish reason;
- request ID where supplied.

No provider SDK response object leaves the adapter.

---

## 9. Streaming generation

Streaming means the application receives pieces of the model's answer as they are generated instead of waiting for the whole answer.

For example, the provider might send these pieces:

1. `"Hello"`
2. `" world"`
3. `"! "`

Serviq must preserve them exactly. Removing the leading space in the second chunk would accidentally produce:

`Helloworld!`

The OpenRouter adapter therefore yields C-4 `GatewayStreamEvent` objects in provider order without trimming provider-generated text.

At the end of the stream, the adapter normalizes terminal metadata such as:

- finish reason;
- usage;
- request ID.

A stream that ends without meaningful terminal information fails safely rather than pretending completion happened normally.

---

## 10. The OpenRouter-specific mid-stream error problem

This is one of the most important differences between a simple OpenAI copy and a production OpenRouter adapter.

Imagine OpenRouter has already streamed:

`"Your order refund is"`

Then the upstream model provider disconnects.

The HTTP connection has already started successfully. The server cannot go back in time and change the original HTTP status from 200 to 502.

OpenRouter can therefore send the failure **inside the response stream** as an error object.

This is called an **in-band error**: the error travels inside what otherwise looks like normal response data.

If Serviq ignored that error, it could return partial text as if it were a successful completed answer.

OPE-297 explicitly checks OpenRouter stream chunks for embedded error data before treating them as successful C-4 output.

The adapter reads only enough information to classify the failure:

- the error's numeric code;
- OpenRouter's stable `error_type` when available.

It deliberately ignores the raw provider message when constructing the public C-4 error.

Tests prove that a rate-limit error arriving after partial text becomes `PROVIDER_RATE_LIMITED`, not a successful partial completion.

---

## 11. Non-stream in-band provider failures

OpenRouter can also represent a provider failure inside a non-stream Chat Completions response after partial provider work has happened.

Such a response may contain:

- partial generated text;
- `finish_reason = error`;
- an embedded provider error object.

OPE-297 checks the embedded error before returning content.

This prevents a response such as:

`"partial output"`

from being treated as a normal successful answer when OpenRouter has explicitly said the provider failed.

The test suite verifies that the partial content never appears in the normalized public error.

---

## 12. Structured JSON output

C-4 can request a JSON object matching a supplied JSON Schema.

A **JSON Schema** is a machine-readable description of what fields and data types a JSON result should contain.

For example, a schema might require:

- `answer` to be a string;
- no unknown additional fields.

OpenRouter supports JSON Schema structured output for compatible models.

When C-4 requests structured output, the adapter sends an OpenAI-compatible response format containing:

- `type = json_schema`;
- `strict = true`;
- the already validated C-4 schema.

The returned text is parsed into Serviq's own `structured` dictionary.

If the provider returns malformed JSON, Serviq fails safely rather than trusting broken structured data.

For structured streaming, JSON fragments are buffered until the stream is complete, then parsed and emitted as a C-4 `structuredDelta`.

---

## 13. Timeout and token budgets

C-4 already places upper limits on:

- how long a provider request may run;
- how many output tokens may be requested.

OPE-297 forwards those validated limits rather than inventing provider-specific values.

The request uses:

`max_completion_tokens = request.max_output_tokens`

and the request timeout is derived from:

`request.timeout_ms`

OpenRouter's current Chat Completions API supports `max_completion_tokens`, so the adapter does not need to translate the budget into an older deprecated parameter.

---

## 14. Why hidden retries are disabled

The OpenAI SDK can automatically retry some failed HTTP calls.

OPE-297 creates the provider client with:

`max_retries = 0`

Why disable retries?

Imagine Serviq thinks it made one model call, but the SDK silently made three attempts.

That could:

- increase cost;
- exceed the visible timeout budget;
- duplicate work;
- make provider telemetry confusing;
- conflict with future Serviq-owned fallback logic.

Serviq wants retry/fallback behavior to be explicit at the orchestration layer above the provider adapter.

---

## 15. Provider-specific features intentionally not exposed

OpenRouter has many useful features beyond basic model generation, including:

- provider preferences;
- model fallback arrays;
- plugins;
- web search;
- routing controls;
- attribution metadata;
- extra debugging metadata.

OPE-297 does not automatically expose those features through C-4.

This is deliberate.

If a provider adapter could add arbitrary provider-specific options to a shared request, C-4 would slowly stop being provider-neutral.

The OpenRouter adapter therefore does not send caller-controlled:

- `extra_body`;
- plugin definitions;
- provider-routing rules;
- fallback model lists;
- arbitrary provider headers;
- router metadata controls.

Those can be introduced later only when the product actually needs them and the shared architecture decides where they belong.

---

## 16. Error normalization

Every AI provider has different exception classes and error bodies.

Serviq does not want product code to contain rules like:

> If OpenRouter returned this Python exception, do one thing, but if Gemini returned that Google exception, do another thing.

C-4 therefore owns five normalized provider error categories.

OPE-297 maps failures into:

| Provider condition | Serviq C-4 result |
|---|---|
| invalid/missing credentials or permission | `PROVIDER_AUTH_FAILED` |
| rate limit | `PROVIDER_RATE_LIMITED` |
| timeout | `PROVIDER_TIMEOUT` |
| network/provider/server failure | `PROVIDER_UNAVAILABLE` |
| invalid model/schema/request or another applicable request error | `PROVIDER_INVALID_REQUEST` |

The same mapping is applied whether the failure arrives as:

- a normal OpenAI-SDK exception;
- an OpenRouter embedded response error;
- a mid-stream OpenRouter error event.

---

## 17. Why raw provider error text is discarded

Provider errors can contain more information than Serviq wants to expose.

Depending on the underlying provider, a raw error could contain:

- internal provider implementation details;
- HTML error pages;
- upstream provider names;
- parts of the request;
- debugging metadata;
- accidentally echoed sensitive values.

The OpenRouter adapter uses fixed Serviq-written error messages.

Tests construct fake errors containing:

- a fake OpenRouter API key;
- strings containing `raw` provider content;
- HTML-like provider text;
- partial generated output.

The normalized Serviq error must not contain any of those values.

---

## 18. Request-scoped client cleanup

The provider client owns HTTP resources such as connections.

The OpenRouter adapter closes its async client after a request succeeds or fails.

Cleanup errors are suppressed.

That may sound unusual, but it protects the adapter boundary.

Suppose the provider call already returned a safe normalized rate-limit error, and then closing the HTTP client raised a low-level library exception. The cleanup exception should not replace the useful normalized result with provider SDK details.

So cleanup is best-effort and cannot change the public provider outcome.

---

## 19. Runtime dependency impact

OPE-297 does **not** add another provider library.

It reuses:

`openai==2.53.0`

which was already present in the LLM Gateway.

The OpenRouter adapter therefore adds provider functionality without expanding the runtime dependency tree.

During OPE-296, the repository's Security workflow was also improved so LLM Gateway Python dependencies are explicitly vulnerability-audited. The shared SDK used by OpenAI and OpenRouter is therefore covered by that security gate.

A future OpenAI SDK upgrade now needs regression testing for both adapters because both provider implementations depend on that transport library.

---

## 20. Tests added

`services/llm-gateway/tests/test_openrouter_adapter.py` validates the provider boundary without making real network calls.

The test suite covers:

1. the default client uses the exact OpenRouter base URL;
2. SDK retries are disabled;
3. successful non-stream generation;
4. exact validated upstream-model forwarding;
5. output-token forwarding;
6. timeout forwarding;
7. system/user/assistant message order;
8. normalized provider identity;
9. token usage normalization;
10. finish-reason normalization;
11. request-ID normalization;
12. C-4 rejection of arbitrary `baseUrl` and `endpoint` fields;
13. JSON Schema structured output;
14. ordered text streaming;
15. streaming whitespace preservation;
16. usage/finish/request metadata at stream completion;
17. structured streaming;
18. authentication error normalization;
19. rate-limit normalization;
20. timeout normalization;
21. network/provider-unavailable normalization;
22. invalid-request normalization;
23. raw SDK error and fake-key redaction;
24. typed OpenRouter embedded authentication error normalization;
25. typed embedded rate-limit error normalization;
26. typed embedded timeout normalization;
27. typed embedded provider-unavailable normalization;
28. typed embedded invalid-request normalization;
29. mid-stream embedded error detection after partial content;
30. non-stream partial-output provider failure detection;
31. missing-key fail-closed behavior;
32. provider-context mismatch behavior;
33. wrong stream/non-stream API path behavior;
34. malformed structured-output handling;
35. empty-stream handling;
36. provider SDK types remaining behind the C-4 boundary.

The injected fake client records request arguments and returns fake provider responses. No required CI test uses a real OpenRouter account, real key, network request, or provider credit.

---

## 21. Security review

The full premium security review is stored at:

`docs/security-reviews/OPE-297-openrouter-adapter.md`

It covers:

- fixed outbound destination;
- SSRF/proxy risk;
- BYOK key handling;
- provider-context binding;
- model ownership;
- provider-routing exclusions;
- timeout/retry control;
- structured output;
- stream integrity;
- in-band provider failures;
- raw-error containment;
- SDK-type containment;
- client cleanup;
- dependency security;
- mock-only tests.

---

## 22. Files changed by OPE-297

The implementation adds or updates these main files:

### Architecture

`docs/architecture-decisions/ADR-013-openrouter-transport-baseline.md`

Defines the approved OpenRouter transport and security boundary.

### Runtime adapter

`services/llm-gateway/app/adapters/openrouter.py`

Contains the provider-specific translation and normalization logic.

### Adapter package export

`services/llm-gateway/app/adapters/__init__.py`

Exports `OpenRouterAdapter` alongside the other provider adapters.

### Automated tests

`services/llm-gateway/tests/test_openrouter_adapter.py`

Contains mocked provider contract/security tests.

### Original blocker reconciliation

`docs/architecture-blockers/OPE-297-openrouter-transport-decision.md`

Preserves the original stop-condition history and records how ADR-013 resolved it.

### Security review

`docs/security-reviews/OPE-297-openrouter-adapter.md`

Documents the production trust-boundary review.

### Plain-language implementation guide

`docs/OPE_297_IMPLEMENTATION.md`

This document.

### Cumulative project build guide

`docs/SERVIQ_BUILD_GUIDE.md`

Receives the OPE-297 follow-up before final ticket closure.

---

## 23. What OPE-297 intentionally does not build

OPE-297 does not include:

- OpenRouter model CRUD;
- provider connectivity testing;
- model alias CRUD;
- automatic model fallback;
- cheapest-model routing;
- provider preference configuration;
- OpenRouter plugins;
- web-search configuration;
- arbitrary provider endpoints;
- arbitrary request headers;
- a new secret-storage path;
- agent runtime behavior;
- new OpenRouter-specific C-4 fields.

These are separate product or architecture decisions.

---

## 24. What improves for Serviq

### Another provider becomes interchangeable

Agent/domain code can use C-4 rather than importing OpenRouter or OpenAI SDK types.

### Endpoint control stays server-owned

A tenant cannot turn the LLM Gateway into a generic proxy by supplying a custom provider URL.

### Validated model configuration remains authoritative

The adapter sends only the already resolved upstream model.

### OpenRouter partial failures are safer

An in-band failure after partial generation does not become a misleading successful answer.

### Failure handling is consistent

Callers receive the same five C-4 provider error categories used by the other adapters.

### Tests remain deterministic and free

CI does not depend on OpenRouter uptime or provider spend.

### Dependency growth is avoided

The implementation reuses the already approved SDK rather than introducing another package.

---

## 25. Completion checklist

OPE-297 should be marked Done only when all of these are true:

- [x] OpenRouter transport decision exists in ADR-013;
- [x] architecture PR #141 passed CI and Security and merged;
- [x] a fresh runtime branch was created from architecture-approved `main`;
- [x] fixed OpenRouter base URL is implemented;
- [x] non-stream generation is implemented behind C-4;
- [x] streaming is implemented behind C-4;
- [x] validated upstream model is passed exactly;
- [x] arbitrary endpoint fields are rejected;
- [x] structured output is supported without changing C-4;
- [x] normal SDK errors are normalized;
- [x] OpenRouter embedded/mid-stream errors are normalized;
- [x] raw provider/key material is contained;
- [x] mock/fake-only tests are implemented;
- [x] premium security review is version-controlled;
- [x] detailed plain-language implementation documentation exists;
- [ ] cumulative `SERVIQ_BUILD_GUIDE.md` follow-up is finalized;
- [ ] final lint/type/test/Compose/database checks pass on the exact final PR head;
- [ ] final Security workflow passes on the exact final PR head;
- [ ] runtime PR #142 is merged to `main`;
- [ ] GitHub issue #128 is closed as completed;
- [ ] Linear OPE-297 is moved to Done.

Unchecked items remain unchecked until the exact final merged implementation satisfies them. Documentation is not used as a substitute for validated runtime code.