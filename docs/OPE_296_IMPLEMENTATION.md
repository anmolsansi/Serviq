# OPE-296 — Gemini generation and streaming adapter implementation

## Who this document is for

This document explains OPE-296 in plain language. It is intentionally written so that a new intern, a non-technical product person, or a high-school student can understand what was changed, why it was changed, what risks were considered, and how we know the work is correct.

Technical terms are explained as they appear instead of assuming the reader already knows them.

---

## 1. What problem OPE-296 solves

Serviq is designed to work with more than one AI provider. Today that includes providers such as OpenAI, Anthropic, Gemini, and later OpenRouter.

The dangerous way to support multiple providers is to let the whole application know how every provider works. For example, one part of the product might directly construct an OpenAI request while another part constructs a Gemini request. Over time, the application becomes tied to provider-specific libraries, names, errors, and response formats.

Serviq avoids that problem with **Contract C-4**.

A contract is simply an agreed shape for information. C-4 says, in effect:

> “The rest of Serviq talks to one Serviq-owned AI interface. A small provider adapter translates that request into whatever OpenAI, Anthropic, Gemini, or another provider needs.”

OPE-296 adds the Gemini translation layer.

After this ticket, product and agent code should not need to know:

- what a Google Gen AI SDK object looks like;
- that Gemini calls an assistant message a `model` message;
- how Gemini represents token usage;
- which Google exception represents a bad request;
- how Gemini streams chunks;
- how JSON Schema structured output is configured in the Google SDK.

Those details remain inside one file: `services/llm-gateway/app/adapters/gemini.py`.

---

## 2. Why implementation originally stopped

The first investigation of OPE-296 did **not** add Gemini code. That was intentional.

The ticket explicitly required the implementation to stop if the repository had not already approved which Gemini SDK to use.

At that time, `ADR-011-provider-sdk-baseline.md` approved only:

- `openai==2.53.0`;
- `anthropic==0.121.0`.

It explicitly did not approve a Gemini dependency.

Choosing a library inside the feature ticket would have quietly made an architectural decision. A library choice affects:

- supply-chain/security risk;
- Python compatibility;
- request and streaming APIs;
- retry behavior;
- timeout behavior;
- exception types;
- future maintenance and upgrades.

So the earlier implementation correctly stopped and recorded a `Needs Architect Decision` blocker.

---

## 3. How the blocker was resolved

A new architecture decision, `ADR-012-gemini-sdk-baseline.md`, was created and merged through GitHub PR #136.

The decision approves:

- Google's official `google-genai` package;
- exact version `2.17.0`;
- Python 3.14 support;
- Gemini Developer API mode;
- tenant-owned API keys resolved by Serviq before the adapter runs;
- one provider attempt, with no hidden SDK retry loop;
- the existing C-4 timeout and output-token limits;
- native JSON Schema structured output;
- asynchronous generation and streaming;
- C-4's existing five safe provider error categories.

This matters because the feature code now follows a written, reviewable decision instead of making the decision itself.

---

## 4. Files changed by the implementation

### `services/llm-gateway/pyproject.toml`

Adds the approved provider dependency:

- `google-genai==2.17.0`

It also pins `httpx==0.28.1` as a direct gateway dependency because the adapter deliberately recognizes `httpx` timeout and transport failures when converting them into Serviq's safe error categories.

The important idea is that the adapter should understand provider-network failures but should not expose them to the rest of Serviq.

### `services/llm-gateway/app/adapters/gemini.py`

This is the production Gemini adapter.

It contains all Gemini-specific request translation, response normalization, streaming behavior, structured-output handling, client construction, error normalization, and client cleanup.

### `services/llm-gateway/app/adapters/__init__.py`

Exports `GeminiAdapter` from the provider-adapter package, following the same package structure already used for OpenAI and Anthropic.

### `services/llm-gateway/tests/test_gemini_adapter.py`

Adds mocked tests for the entire Gemini C-4 boundary. The tests do not call Gemini over the internet and do not spend provider credits.

### `docs/security-reviews/OPE-296-gemini-adapter.md`

Records the premium security review: secret handling, endpoint control, retries, timeouts, data minimization, error redaction, and provider-type containment.

### `docs/architecture-blockers/OPE-296-gemini-sdk-decision.md`

Changes the old blocker record from `Needs Architect Decision` to `Resolved by ADR-012 / PR #136`, while preserving the history of why implementation originally stopped.

### `docs/OPE_296_IMPLEMENTATION.md`

This document.

---

## 5. How a normal Gemini request now works

Imagine Serviq wants an AI model to summarize a customer-support case.

The rest of the application creates a C-4 request. It may contain:

1. a system instruction such as “Follow support policy.”;
2. customer/user text;
3. previous assistant text;
4. a maximum number of output tokens;
5. a timeout;
6. an optional JSON response schema;
7. whether the request should stream.

Before OPE-296, Gemini could not consume that request through a production adapter.

After OPE-296, the flow is:

1. Serviq validates the C-4 request.
2. Higher-level routing resolves the tenant's Gemini provider connection.
3. Higher-level model configuration resolves the real Gemini model string.
4. Higher-level secret handling resolves the tenant's API key into `AdapterContext`.
5. `GeminiAdapter` verifies that the context really belongs to Gemini.
6. The adapter translates C-4 message roles into Gemini roles.
7. It builds an official Google SDK configuration using only bounded C-4 values.
8. The Google SDK performs one upstream request.
9. The adapter converts Google's response into a Serviq-owned `GatewayResponse`.
10. No Google response object or exception is returned to agent/domain code.

The rest of Serviq therefore receives the same kind of object it would receive from another C-4 provider adapter.

---

## 6. Message translation

Different AI providers use slightly different names for conversation roles.

C-4 uses:

- `system`;
- `user`;
- `assistant`.

Gemini uses:

- a separate `system_instruction` configuration;
- `user` for user-authored messages;
- `model` for model-authored/assistant messages.

The adapter translates them like this:

| C-4 concept | Gemini representation |
| --- | --- |
| leading `system` message | `system_instruction` |
| `user` | `user` |
| `assistant` | `model` |

If there are multiple leading system messages, the adapter preserves their order and joins them with a blank line.

The adapter does **not** move a system message from the middle of an existing conversation to the beginning. Doing that would silently alter what the caller sent.

Instead, a late system message returns `PROVIDER_INVALID_REQUEST`.

A request containing only system instructions and no conversation message is also rejected explicitly.

This is an example of **fail closed** behavior: when the adapter cannot preserve the requested meaning safely, it reports the limitation instead of guessing.

---

## 7. API-key safety

Serviq uses a **BYOK** model. BYOK means “Bring Your Own Key.” A tenant supplies its own provider credential, and Serviq stores/resolves that credential through the platform's secret boundary.

OPE-296 does not change secret storage.

The Gemini adapter receives a `SecretStr` only after higher-level code has selected the provider for the current tenant.

The adapter will not accept a Gemini key through:

- request JSON;
- `modelAlias`;
- query parameters;
- arbitrary end-user headers;
- an arbitrary provider URL.

If the key is missing or blank, the request fails with the safe Serviq code `PROVIDER_AUTH_FAILED`.

The raw key is never returned in a C-4 response or error.

---

## 8. Why Gemini Developer API mode is forced explicitly

The Google SDK can work with different Google AI backends. Environment settings may be able to influence which backend the SDK uses unless code makes the choice explicit.

That is undesirable for Serviq's tenant BYOK path.

The client factory therefore constructs the SDK using:

`enterprise=False`

In simple terms, this says:

> “This adapter is for the Gemini Developer API. Do not let a machine-level environment variable quietly turn it into an enterprise/Vertex request.”

The caller also cannot provide a base URL, project, location, or enterprise flag through C-4.

This reduces configuration ambiguity and avoids turning the adapter into a generic arbitrary-endpoint proxy.

---

## 9. Timeouts and retries

A timeout is how long Serviq is willing to wait for a provider request.

A retry means automatically trying a failed request again.

Retries sound harmless, but they can be dangerous for generative AI calls because they may:

- generate twice;
- spend more money than expected;
- exceed the caller's timeout;
- create duplicate effects if generation later triggers an action;
- make observability inaccurate because Serviq thinks it made one request while the SDK made several.

C-4 already caps timeout and maximum output tokens.

The Gemini adapter forwards those validated limits and sets:

- the exact C-4 timeout in the Google SDK's HTTP options;
- `HttpRetryOptions(attempts=1)`.

One attempt means the provider SDK does not secretly retry underneath Serviq.

Any future retry/fallback policy should be implemented at the Serviq orchestration layer where the system can observe and control it.

---

## 10. Non-stream generation

A non-stream request waits for the provider to finish and returns one completed answer.

For Gemini, the adapter calls the official asynchronous `generate_content` API.

The adapter then normalizes:

- generated text;
- provider = `gemini`;
- the already-resolved upstream model;
- input-token count, when supplied;
- output-token count, when supplied;
- finish reason;
- provider response/request ID, when supplied.

The returned object is a Serviq `GatewayResponse`, not a Google `GenerateContentResponse`.

That distinction is central to the architecture: Google types end at the adapter boundary.

---

## 11. Streaming

Streaming means the model sends pieces of the answer while it is generating instead of waiting for the entire response.

For example, the provider might send:

1. `"Hello"`
2. `" world"`
3. `"! "`

Notice that the second piece begins with a space and the third ends with one.

The adapter preserves those chunks exactly. It does not trim provider-generated text.

If downstream code joins the pieces, it receives:

`"Hello world! "`

instead of accidentally changing it to something like `"Helloworld!"`.

The adapter emits Serviq-owned `GatewayStreamEvent` objects and adds terminal metadata such as finish reason, usage, and response ID when available.

An empty provider stream with no terminal information is treated as `PROVIDER_UNAVAILABLE`, not as a successful empty answer.

---

## 12. Structured output

Sometimes Serviq does not want free-form text. It wants a JSON object with a predictable shape.

For example:

```json
{
  "answer": "resolved"
}
```

C-4 carries an optional `responseSchema`, which is a JSON Schema describing the required structure.

The Gemini adapter does not ignore this field.

It configures the official SDK with:

- `response_mime_type = application/json`;
- `response_json_schema = <the C-4 schema>`.

When Gemini responds, the adapter parses the JSON into a Serviq-owned dictionary.

If Gemini returns malformed JSON, the adapter fails instead of sending malformed provider text downstream as if it were valid structured data.

For structured streaming, individual JSON fragments are buffered until the stream finishes, then validated and emitted as a proper `structuredDelta`.

---

## 13. Provider error normalization

Every provider has different exception classes and error payloads. Exposing those directly would make the rest of Serviq provider-dependent and could leak sensitive upstream details.

C-4 deliberately has only five provider error categories.

OPE-296 maps Gemini failures like this:

| Gemini/provider condition | Serviq C-4 code |
| --- | --- |
| 401/403 authentication or permission failure | `PROVIDER_AUTH_FAILED` |
| HTTP 429 | `PROVIDER_RATE_LIMITED` |
| timeout / HTTP 408 | `PROVIDER_TIMEOUT` |
| network transport failure / provider 5xx | `PROVIDER_UNAVAILABLE` |
| invalid model, schema, request, unsupported provider capability, other applicable 4xx | `PROVIDER_INVALID_REQUEST` |

The error message is written by Serviq.

The adapter intentionally does not reuse the raw Google exception string because upstream error text may contain:

- request details;
- provider implementation details;
- arbitrary raw response content;
- identifiers;
- in the worst case, accidentally echoed secret material.

The tests construct provider exceptions containing fake secret/raw text and prove the normalized C-4 error does not contain it.

---

## 14. Why `httpx` is a direct dependency

The Google SDK uses HTTP transport underneath the provider call.

OPE-296 directly recognizes `httpx` timeout and transport exceptions so it can distinguish:

- a timeout, which becomes `PROVIDER_TIMEOUT`;
- a transport/network failure, which becomes `PROVIDER_UNAVAILABLE`.

Because production adapter code imports `httpx` classes directly, the gateway declares the compatible package directly rather than relying on it only as an undeclared transitive dependency of another library.

This makes the adapter's dependency on those exception types explicit and reviewable.

---

## 15. Client cleanup

The Google SDK owns HTTP client resources.

The Gemini adapter creates a request-scoped client and closes both its asynchronous and synchronous resources after the request succeeds or fails.

Cleanup errors are deliberately suppressed.

Why? Suppose the provider call already produced a valid normalized failure, but closing a socket then raised an SDK-specific cleanup exception. That cleanup exception should not replace the safe C-4 result and escape the adapter boundary.

Cleanup is therefore best-effort and cannot change the normalized provider outcome.

---

## 16. Tests added

The automated test file validates the important behavior without calling Gemini over the network.

The suite covers:

1. successful non-stream generation;
2. normalized provider/model/usage/finish/request metadata;
3. system instruction translation;
4. `user -> user` translation;
5. `assistant -> model` translation;
6. preservation of conversation order;
7. C-4 max-output-token forwarding;
8. C-4 timeout forwarding;
9. one-attempt/no-hidden-retry configuration;
10. explicit Gemini Developer API client mode;
11. structured JSON response configuration;
12. structured JSON response normalization;
13. streaming order;
14. streaming whitespace preservation;
15. terminal streaming metadata;
16. structured streaming;
17. authentication error normalization;
18. rate-limit normalization;
19. timeout normalization;
20. provider-outage normalization;
21. invalid-request normalization;
22. provider raw error/key redaction;
23. late system-message rejection;
24. system-only request rejection;
25. malformed structured provider response rejection;
26. missing credential failure;
27. provider-context mismatch failure;
28. misuse of stream/non-stream paths;
29. empty stream failure;
30. return-type containment at the Serviq C-4 boundary.

The fake client records what would have been sent to Google, allowing the test to inspect request translation without making a real provider call.

---

## 17. What this implementation does not do

OPE-296 deliberately does **not** implement:

- model alias CRUD;
- arbitrary Gemini model selection from user request content;
- provider connectivity testing;
- OpenRouter support;
- provider fallback;
- retry orchestration;
- secret storage;
- Vertex/enterprise deployments;
- arbitrary provider base URLs;
- agent-runtime logic;
- a Gemini-specific field added to C-4.

Keeping this scope narrow prevents one provider ticket from changing unrelated architecture.

---

## 18. Security improvements

The implementation improves Serviq's security posture in several concrete ways:

- **Secret containment:** only server-resolved keys reach the adapter.
- **Provider binding:** a non-Gemini context is rejected before provider interaction.
- **Endpoint control:** callers cannot supply provider endpoints or enterprise routing.
- **Environment hardening:** Developer API mode is explicit.
- **Cost/time control:** C-4 token and timeout caps remain authoritative.
- **No hidden retries:** one SDK attempt prevents invisible duplicate provider calls.
- **Data minimization:** only C-4-approved provider metadata returns.
- **Error redaction:** raw provider errors and key material are discarded.
- **SDK isolation:** Google types do not spread into product/domain code.
- **No live CI provider calls:** tests are deterministic and do not require production credentials.

The full security analysis lives in `docs/security-reviews/OPE-296-gemini-adapter.md`.

---

## 19. What improves for the product

Before OPE-296, Gemini existed in the provider enum and product architecture but did not have a production implementation behind C-4.

After OPE-296 is merged and validated:

- Gemini can be treated as another provider implementation at the gateway boundary;
- agent/domain code remains provider-neutral;
- tenant BYOK credentials stay behind the existing secret boundary;
- provider errors behave consistently with OpenAI/Anthropic;
- streaming clients receive the same Serviq event model;
- structured output is normalized into the same C-4 data shape;
- changing Google SDK internals later is localized to the adapter rather than the whole product.

This is a maintainability improvement as much as a feature addition.

---

## 20. How OPE-296 is considered complete

The ticket should be marked Done only after all of these are true:

- [x] an approved Gemini SDK/transport decision exists (`ADR-012`);
- [x] the exact provider dependency is declared;
- [x] Gemini non-stream generation is implemented behind C-4;
- [x] Gemini streaming is implemented behind C-4;
- [x] unsupported/invalid message layouts fail explicitly;
- [x] structured output is supported without changing C-4;
- [x] provider errors are normalized into the five C-4 categories;
- [x] provider SDK objects remain internal;
- [x] mocked adapter tests are written;
- [x] premium security review is documented;
- [ ] final lint passes;
- [ ] final strict type checking passes;
- [ ] final automated test suite passes;
- [ ] final GitHub Security workflow passes;
- [ ] implementation PR is merged to `main`;
- [ ] GitHub issue #127 is closed as completed;
- [ ] Linear OPE-296 is moved to Done.

The unchecked items are intentionally left unchecked until GitHub validates the **final implementation PR head**. Documentation is not used as a substitute for runtime validation.

---

## 21. Related records

- Linear: OPE-296 — V1.2.08 Implement Gemini generation and streaming adapter
- GitHub issue: #127
- Initial blocker PR: #131
- Batch blocker/documentation PR: #135
- Architecture decision PR: #136
- Runtime implementation PR: #137
- Architecture decision: `docs/architecture-decisions/ADR-012-gemini-sdk-baseline.md`
- Security review: `docs/security-reviews/OPE-296-gemini-adapter.md`
- Historical blocker record: `docs/architecture-blockers/OPE-296-gemini-sdk-decision.md`
- Cumulative product/build explanation: `docs/SERVIQ_BUILD_GUIDE.md`
