

---

# OPE-296 follow-up — Gemini adapter architecture decision and runtime implementation

> **Status correction to the earlier OPE-296–OPE-299 blocker section:** the earlier section correctly recorded that OPE-296 was blocked at that time. That blocker has now been resolved by ADR-012, and the Gemini runtime adapter has been implemented and validated in PR #137. OPE-297, OPE-298, and OPE-299 are unaffected by this update and keep their previously documented status.

## Why this follow-up exists

The original OPE-296 investigation found that Serviq had no architecture-approved Gemini SDK. The ticket explicitly required implementation to stop in that situation, so the first OPE-296 branch added only the blocker record.

That was the correct state then, but it is no longer the current state.

This follow-up records the complete chain from blocker to implementation so a reader does not have to reconstruct the story from several GitHub issues and pull requests.

The lifecycle is now:

1. OPE-296 was investigated.
2. The explicit `Needs Architect Decision` stop condition was found.
3. The blocker was documented instead of guessed around.
4. An architect decision was researched and written.
5. The architecture PR passed CI and Security and was merged.
6. OPE-296 moved to In Progress.
7. A fresh implementation branch was created from the architecture-approved `main` branch.
8. The Gemini dependency was added as an exact pin.
9. The provider-local adapter was implemented behind C-4.
10. Mocked contract tests were added.
11. The premium security review and a plain-language implementation guide were added.
12. The implementation head passed repository CI and Security before this cumulative documentation finalization.
13. The implementation PR must still pass the final post-documentation run and merge before the ticket is closed.

## Architecture decision that unblocked the ticket

The new decision is:

`docs/architecture-decisions/ADR-012-gemini-sdk-baseline.md`

It was developed on:

`agent/ope-296-gemini-sdk-adr`

and merged through GitHub PR #136.

The architecture PR passed the normal Serviq CI and Security workflows and was squash-merged to `main` as:

`002ec7acabd4c8bc44e6319b181e485c11c89005`

### What ADR-012 freezes

Serviq now explicitly approves:

- Google's official `google-genai` package;
- exact version `google-genai==2.17.0`;
- the Gemini Developer API for this tenant-BYOK adapter;
- Python 3.14 compatibility as a requirement;
- server-resolved provider credentials only;
- no caller-controlled Gemini base URL/project/location/enterprise mode;
- explicit Developer API mode rather than environment-selected enterprise routing;
- C-4 as the only shared request/response contract;
- Serviq-owned timeout and retry policy;
- one provider attempt/no hidden SDK retry loop;
- leading C-4 system messages mapped to Gemini system instructions;
- C-4 `assistant` translated internally to Gemini `model`;
- native JSON Schema structured output when C-4 requests it;
- asynchronous normal and streaming generation;
- the existing five safe C-4 provider error categories;
- mock/fake-only required CI tests;
- a premium security review before the runtime merge.

### Why an ADR was necessary

Choosing a provider SDK is not just a syntax choice. It determines dependency provenance, Python compatibility, streaming behavior, timeout/retry behavior, provider exception types, structured-output capabilities, security review surface, and upgrade responsibility.

OPE-296 was a builder ticket, not an architecture ticket. Resolving that choice separately keeps Serviq's contract discipline real instead of allowing the first implementation to become architecture by accident.

## Runtime implementation branch and PR

The runtime work is on:

`agent/ope-296-gemini-adapter-implementation`

GitHub PR:

`#137 — feat: implement Gemini C-4 adapter for OPE-296`

The branch was created from `main` **after** ADR-012 was merged, so the runtime implementation starts from the architecture-approved state rather than from the old blocked branch.

## Micro-level implementation changes

The work was intentionally committed in small changes so each step can be understood and reviewed independently.

### 1. Add the approved SDK dependency

Commit:

`30fdd497d3dd23eeff29476d362e181beec78189`

Changed:

`services/llm-gateway/pyproject.toml`

Added:

- `google-genai==2.17.0`;
- `httpx==0.28.1`.

`google-genai` is the architecture-approved provider library.

`httpx` is declared directly because production adapter code deliberately recognizes its timeout and transport exception classes. Depending on those classes only through an undeclared transitive dependency would hide a real production dependency.

### 2. Implement the Gemini C-4 adapter

Commit:

`3298a9999e9d8b626b052f3584e03736b726ea8b`

Added:

`services/llm-gateway/app/adapters/gemini.py`

The adapter implements:

- non-stream generation;
- ordered streaming;
- system/user/assistant translation;
- upstream-model forwarding from resolved `AdapterContext` only;
- output-token and timeout forwarding from already validated C-4 values;
- native structured JSON Schema configuration;
- response text/structured normalization;
- input/output token normalization;
- finish-reason normalization;
- provider response ID normalization when supplied;
- auth/rate-limit/timeout/unavailable/invalid-request normalization;
- request-scoped SDK cleanup;
- provider SDK type containment.

### 3. Harden fail-closed behavior and endpoint mode

Commit:

`d8adab21405c88385dbe7692f9f844fad0ec54a9`

This follow-up changed two important security/correctness details.

First, it explicitly builds the Google client with `enterprise=False`.

Why: the Google SDK supports more than one Google AI backend. A tenant BYOK request must not be redirected because of an unrelated machine-level enterprise/Vertex environment variable. This adapter owns one approved mode: Gemini Developer API.

Second, provider-specific message validation now runs **before** the SDK client is created.

Why: if a C-4 message layout cannot be represented safely by Gemini, Serviq should reject it before unnecessarily handing the tenant key to provider client construction.

The commit also uses safe cleanup suppression so a provider-specific cleanup exception cannot replace an already normalized C-4 result.

### 4. Export the new adapter

Commit:

`10faf9914dc54e9c1a5e6a81927c4597487c2063`

Changed:

`services/llm-gateway/app/adapters/__init__.py`

`GeminiAdapter` now follows the same package-level adapter export pattern as OpenAI and Anthropic.

### 5. Add mocked C-4 contract tests

Commit:

`dcff12bfd564cf5669024e067ef45b6f8cf8ca03`

Added:

`services/llm-gateway/tests/test_gemini_adapter.py`

The tests use a fake injected Google client. No required test makes a real Gemini call, requires a real tenant key, spends provider credits, or depends on external Gemini availability.

The coverage verifies:

- non-stream success;
- normalized provider/model/usage/finish/request metadata;
- multiple leading system messages;
- `user -> user` mapping;
- `assistant -> model` mapping;
- conversation order;
- maximum output-token forwarding;
- timeout forwarding;
- one-attempt/no-hidden-retry configuration;
- Developer API mode being forced even if an enterprise environment variable exists;
- structured JSON Schema configuration;
- structured output normalization;
- streaming order;
- streaming whitespace preservation;
- streaming terminal metadata;
- structured streaming;
- authentication failure normalization;
- 429/rate-limit normalization;
- timeout normalization;
- provider outage normalization;
- invalid-request normalization;
- raw provider-error and fake-key redaction;
- late system-message rejection;
- system-only request rejection;
- malformed structured-output rejection;
- missing-key failure;
- wrong-provider context failure;
- wrong stream/non-stream path failure;
- empty-stream failure;
- Serviq-owned return types rather than Google SDK return types.

## Message translation in simple terms

C-4 uses the roles:

- `system`;
- `user`;
- `assistant`.

Gemini uses a separate system instruction plus conversation roles `user` and `model`.

The adapter therefore translates:

| Serviq C-4 | Gemini |
|---|---|
| leading `system` | `system_instruction` |
| `user` | `user` |
| `assistant` | `model` |

Multiple leading system messages keep their order and are joined with a blank line.

A system message appearing after normal conversation has started is not silently moved. The adapter returns `PROVIDER_INVALID_REQUEST` because silently changing message order would change the meaning of the request.

A system-only request also fails explicitly because the selected provider path cannot preserve it as a normal conversation.

## Structured output behavior

When C-4 contains `responseSchema`, the adapter uses Gemini's native JSON structured-output configuration instead of ignoring the schema.

It requests:

- MIME type `application/json`;
- the validated C-4 JSON Schema.

The provider's response text is then parsed into Serviq's own `structured` dictionary before leaving the adapter.

Malformed structured output fails closed rather than being passed downstream as trusted structured data.

During structured streaming, partial JSON fragments are buffered and parsed at completion, then emitted as a C-4 `structuredDelta`.

## Timeout, retry, and cost control

C-4 already validates the maximum provider timeout and maximum output tokens.

The Gemini adapter passes those bounded values to the SDK and configures:

`HttpRetryOptions(attempts=1)`

That prevents the provider library from quietly retrying the generation underneath Serviq.

This is important because hidden retries can:

- increase cost;
- create duplicate generation;
- exceed visible time budgets;
- make telemetry inaccurate;
- interfere with future Serviq-owned retry/fallback logic.

Retry/fallback therefore remains an explicit orchestration responsibility above the provider adapter.

## Safe provider error mapping

Gemini-specific exception objects never become the public error contract.

The adapter maps provider conditions to C-4 as follows:

| Provider condition | C-4 code |
|---|---|
| 401/403 | `PROVIDER_AUTH_FAILED` |
| 429 | `PROVIDER_RATE_LIMITED` |
| timeout / provider 408 | `PROVIDER_TIMEOUT` |
| network failure / provider 5xx | `PROVIDER_UNAVAILABLE` |
| invalid model/schema/request or other applicable provider 4xx | `PROVIDER_INVALID_REQUEST` |

The returned messages are fixed Serviq-authored messages.

The raw Google response body, exception string, headers, SDK stack object, and API key are deliberately discarded at this boundary.

## Premium security review

Added:

`docs/security-reviews/OPE-296-gemini-adapter.md`

The review covers:

- SDK/dependency trust boundary;
- tenant BYOK handling;
- provider-context binding;
- endpoint/enterprise routing control;
- timeout/retry ownership;
- message translation;
- structured output;
- streaming integrity;
- metadata minimization;
- raw provider-error redaction;
- resource cleanup;
- logging exposure;
- mock-only testing.

The conclusion is that Gemini remains an implementation detail behind C-4 rather than becoming a new product-wide trust boundary.

## Blocker record reconciliation

Updated:

`docs/architecture-blockers/OPE-296-gemini-sdk-decision.md`

Its status now records:

**Resolved by ADR-012 and PR #136.**

The original blocker explanation remains useful history: it explains why the first implementation attempt intentionally stopped and what decision was required.

This makes the document an audit trail rather than deleting the old rationale after the problem was solved.

## Detailed plain-language implementation document

Added:

`docs/OPE_296_IMPLEMENTATION.md`

It explains the product problem, architecture decision, request flow, message translation, BYOK handling, endpoint hardening, timeout/retry policy, non-stream behavior, streaming behavior, structured output, error normalization, dependency reasoning, cleanup behavior, tests, security improvements, scope exclusions, and completion gates.

## Validation completed before this build-guide finalization

On implementation head:

`ee1afc6a63bdc85f33025815f6553d0d424c9343`

GitHub CI run #174 completed successfully for:

- dependency installation;
- lint;
- strict type checking;
- full repository tests;
- Compose configuration validation;
- real PostgreSQL database integration/migration checks.

GitHub Security run #150 completed successfully for:

- Gitleaks secret scan;
- Trivy filesystem/configuration scan;
- dependency vulnerability audit;
- CodeQL JavaScript/TypeScript;
- CodeQL Python.

This cumulative documentation update creates a newer PR head, so the final merge still requires the workflows to be green on that final head as well.

## What this improves for Serviq

### Gemini becomes a real C-4 provider

Before this work, `gemini` existed in the provider enum and architecture but lacked the production provider adapter.

The runtime implementation now exists without adding Gemini-specific fields to C-4.

### Agent/domain code stays provider-neutral

The rest of Serviq receives `GatewayResponse`, `GatewayStreamEvent`, `GatewayUsage`, and normalized `GatewayProviderError` objects, not Google SDK objects.

### Tenant keys remain behind the existing secret boundary

OPE-296 does not invent a new secret-storage path. It receives only an already resolved `SecretStr` from the gateway context.

### Provider behavior is bounded

The adapter cannot accept a caller-controlled base URL, enterprise mode, Google Cloud project, or location. C-4 timeout/output-token bounds remain authoritative and hidden retries are disabled.

### Failures are predictable

OpenAI, Anthropic, and Gemini can now surface the same five provider-neutral error categories rather than forcing every caller to understand different SDK exception hierarchies.

### Testing is deterministic and free

Required CI tests do not depend on provider uptime, real keys, or paid generation.

## What OPE-296 intentionally does not include

This ticket does not implement:

- OpenRouter;
- provider connectivity testing;
- model configuration CRUD;
- arbitrary model routing/fallback;
- provider retry orchestration;
- Vertex/enterprise Gemini deployment;
- arbitrary provider base URLs;
- agent runtime changes;
- secret-store changes;
- Gemini-specific C-4 extensions.

Those remain separate architectural/product responsibilities.

## OPE-296 closure gate

At the point this follow-up is appended, the implementation and pre-finalization validation are complete, but the ticket is **not yet considered Done solely because this text exists**.

The final closure sequence is:

1. commit this cumulative build-guide update;
2. run CI and Security on the resulting final PR head;
3. make PR #137 ready for review;
4. merge PR #137 only if those final checks remain green;
5. close GitHub issue #127 as completed;
6. move Linear OPE-296 to Done;
7. record the final merge SHA and closure in the ticket comments.

This preserves the rule used throughout Serviq: documentation can explain completion, but only validated merged runtime code can complete a runtime ticket.
