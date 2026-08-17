

# OPE-296 through OPE-299 — architecture-blocked implementation reconciliation

## Why this section exists

OPE-296 through OPE-299 were started using the same disciplined workflow as earlier Serviq tickets: read Linear first, inspect current repository reality, compare it with frozen Architecture/ADRs, create separate GitHub tracking, and only then change production code.

This batch reached an important result: **all four feature tickets triggered their own `Needs Architect Decision` stop conditions before safe production implementation could begin.**

That does not mean nothing was done. It means the repository audit found missing decisions that builder tickets are explicitly forbidden to invent. The correct production-grade behavior was to stop, record the evidence, preserve the branch/issue history, and leave the feature tickets open.

A separate detailed explanation now exists at:

`docs/OPE_296_299_IMPLEMENTATION_GUIDE.md`

Ticket-specific blocker records are under:

`docs/architecture-blockers/`

## Ticket tracking and branch history

| Linear ticket | GitHub issue | Branch | Merged documentation PR | Feature status |
|---|---:|---|---:|---|
| OPE-296 | #127 | `agent/ope-296-gemini-adapter` | #131 | Needs Architect Decision |
| OPE-297 | #128 | `agent/ope-297-openrouter-adapter` | #132 | Needs Architect Decision |
| OPE-298 | #129 | `agent/ope-298-provider-connectivity-test` | #133 | Needs Architect Decision |
| OPE-299 | #130 | `agent/ope-299-model-configuration-crud` | #134 | Needs Architect Decision |

All four ticket PRs passed both CI and Security before merge.

The GitHub issues and Linear tickets remain open/backlogged because documentation of a blocker is not the same as implementing the requested product feature.

---

## OPE-296 — Gemini generation and streaming adapter

### What we were supposed to build

A Gemini implementation behind Serviq's Contract C-4, including non-stream generation, ordered streaming, safe message translation, usage/finish/request-ID normalization, timeout/output limits, provider error normalization, and explicit rejection of unsupported capabilities.

### What repository audit found

ADR-011 freezes only:

- `openai==2.53.0`;
- `anthropic==0.121.0`.

The ADR explicitly says it does not approve Gemini dependencies. `services/llm-gateway/pyproject.toml` therefore has no approved Gemini SDK.

OPE-296 expressly says to stop when no approved Gemini SDK exists in repo context.

### What changed

GitHub issue #127 and branch `agent/ope-296-gemini-adapter` were created.

The branch added:

`docs/architecture-blockers/OPE-296-gemini-sdk-decision.md`

PR #131 passed CI/Security and was squash-merged.

### Why we did not add code anyway

Selecting a Gemini SDK from a builder ticket would silently decide production dependency provenance, Python 3.14 compatibility, streaming behavior, retries, exception semantics, and future upgrade policy. That is exactly the architecture decision the ticket requires to exist first.

### What this improves

It protects C-4/provider neutrality and makes the missing dependency decision visible and reviewable instead of hiding it in implementation code.

### What must happen next

An architect-approved change must freeze the Gemini SDK/transport, exact compatible version or version policy, retry/timeout ownership, Python 3.14 support, reproducibility expectations, and any unsupported C-4 capability behavior.

---

## OPE-297 — OpenRouter generation and streaming adapter

### What we were supposed to build

An OpenRouter C-4 adapter using only a server-resolved BYOK secret and validated upstream model, with fixed Serviq-owned endpoint behavior, streaming/non-stream normalization, error mapping, and no provider-specific leakage.

### What repository audit found

No OpenRouter transport/client choice is frozen. ADR-011 explicitly excludes OpenRouter dependency approval.

Possible approaches exist, such as reusing an OpenAI-compatible client or using direct HTTP, but the ticket says the transport choice must already be frozen. A builder is not authorized to pick one implicitly.

### What changed

GitHub issue #128 and branch `agent/ope-297-openrouter-adapter` were created.

The branch added:

`docs/architecture-blockers/OPE-297-openrouter-transport-decision.md`

PR #132 passed CI/Security and was squash-merged.

### Why this matters

OpenRouter's endpoint/transport decision is security-sensitive because Serviq must never let a tenant turn provider configuration into arbitrary outbound URL control. The stop preserves server ownership of the destination and keeps transport behavior explicit.

### What must happen next

Freeze the OpenRouter transport, dependency/version if any, immutable base URL, caller-override prohibition, provider header policy, timeout/retry ownership, and Python/reproducibility rules.

---

## OPE-298 — Provider connectivity test endpoint

### What we were supposed to build

`POST /api/v1/providers/{providerConnectionId}/test` should perform one fixed, tiny, bounded provider request using the saved tenant credential and return/store only safe normalized status.

The user must not be able to supply an arbitrary prompt, model, endpoint, or provider body.

### What is already frozen

Architecture already defines the route and these built-in rate limits:

- `provider.test.user`: 10/minute;
- `provider.test.connection`: 30/hour.

The provider table also defines `untested|active|invalid|disabled` status values.

### What repository audit found missing

The ticket requires an architecture-approved minimal model-selection strategy. None is frozen in the current repository.

The Architecture also does not define exact persisted status semantics for temporary provider outcomes such as `429`, timeout, or provider unavailable. Those failures do not prove a credential is invalid, so guessing the transition would make provider status misleading.

OPE-296 and OPE-297 are also blocked, meaning a four-provider connectivity test cannot yet use all supported adapters.

### What changed

GitHub issue #129 and branch `agent/ope-298-provider-connectivity-test` were created.

The branch added:

`docs/architecture-blockers/OPE-298-provider-test-contract-decisions.md`

PR #133 passed CI/Security and was squash-merged.

### What this improves

It prevents a supposedly harmless test endpoint from becoming a free-form completion proxy or from marking healthy credentials invalid because of temporary provider conditions.

### What must happen next

Freeze provider-by-provider test-model selection, whether model configuration is required first, transient status transitions, stable test error codes, API-to-gateway invocation boundaries, and finish Gemini/OpenRouter adapter prerequisites.

---

## OPE-299 — Model configuration CRUD and alias validation

### What we were supposed to build

Tenant-scoped CRUD for stable Serviq model configurations through:

- `GET /api/v1/models`;
- `POST /api/v1/models`;
- `PATCH /api/v1/models/{modelConfigurationId}`;
- `DELETE /api/v1/models/{modelConfigurationId}`.

The table already freezes tenant/provider relationship, alias, upstream model, purpose, enabled state, and tenant-unique alias behavior.

### What repository audit found missing

The ticket requires referenced model configurations to be protected from deletion, including a required test where referenced deletion returns conflict.

But there is currently no implemented/frozen authoritative reference from an agent or another configuration to `model_configurations`:

- no current FK points to the table;
- no `model_configuration_id` is implemented elsewhere;
- `agent_versions` is not implemented yet;
- the planned agent JSON `config` does not freeze a model-reference path or whether identity is UUID versus alias.

Therefore the system cannot truthfully determine whether a model configuration is “referenced” without inventing another module's contract.

### What changed

GitHub issue #130 and branch `agent/ope-299-model-configuration-crud` were created.

The branch added:

`docs/architecture-blockers/OPE-299-model-reference-rules.md`

PR #134 passed CI/Security and was squash-merged.

### Why partial CRUD was rejected

A delete endpoint that succeeds simply because agent references are not implemented yet would create a dangerous future compatibility trap. Inventing a new FK or JSON path would be an unauthorized architecture change. The ticket explicitly says to stop in this situation.

### What this improves

It protects future published/deployed agent configuration from silent model deletion or incompatible mutation.

### What must happen next

Freeze how agents/configurations reference a model, what draft/published/deployed references block deletion, which model fields remain mutable after reference, and the authoritative conflict-check mechanism.

---

## Batch-level result

### Completed in this work

- four separate GitHub issues (#127–#130);
- four separate ticket branches;
- current Linear/repository/Architecture/ADR audit for every ticket;
- detailed `Needs Architect Decision` comments on all four Linear tickets;
- visible blocker status in all four GitHub issues;
- four ticket-specific version-controlled blocker documents;
- four ticket PRs (#131–#134), all passing CI and Security before merge;
- detailed batch guide `docs/OPE_296_299_IMPLEMENTATION_GUIDE.md`;
- this cumulative build-guide reconciliation.

### Not completed and not claimed as completed

- Gemini adapter;
- OpenRouter adapter;
- provider connectivity-test runtime endpoint;
- model configuration CRUD runtime API.

### Why this distinction matters

Serviq's builder rules exist to prevent implementation tickets from quietly changing architecture. Calling these tickets “done” because blocker documentation was merged would be misleading. The correct state is: **investigation and blocker documentation complete; feature implementation blocked pending architect decisions.**

## Recommended unblock order

1. Freeze Gemini SDK and OpenRouter transport decisions.
2. Implement/validate OPE-296 and OPE-297.
3. Freeze provider-test model selection and transient status semantics.
4. Implement/validate OPE-298.
5. Freeze model-reference/mutability rules for agents and other configurations.
6. Implement/validate OPE-299.

Only after actual feature code satisfies each ticket's acceptance tests should GitHub issues #127–#130 and their corresponding Linear tickets be closed.
