# Serviq implementation guide — OPE-296 through OPE-299

## Why this document exists

This document explains what happened when OPE-296, OPE-297, OPE-298, and OPE-299 were started.

The important result is unusual but deliberate: **none of the four production features was implemented yet.** That is not because the work was skipped. Each ticket contains an explicit safety rule that says the builder must stop when a required architecture decision has not already been frozen. The repository audit found that every ticket currently reaches one of those stop conditions.

A production-oriented engineering process must distinguish between these two situations:

1. “We have not investigated the work yet.”
2. “We investigated the work, found a contract decision that the feature ticket is not authorized to make, documented the blocker, and intentionally stopped before creating incompatible code.”

OPE-296 through OPE-299 are in the second category.

This guide is written so a non-technical reader can understand what each feature was supposed to do, what was already available in Serviq, what was missing, why guessing would be dangerous, what work was actually completed, and exactly what must happen before implementation resumes.

---

# Batch summary

The four tickets form a connected part of Serviq's AI-provider configuration system:

1. **OPE-296** wants to let the LLM Gateway call Google Gemini.
2. **OPE-297** wants to let the LLM Gateway call OpenRouter.
3. **OPE-298** wants an administrator to test whether a saved provider key actually works.
4. **OPE-299** wants administrators to create stable model aliases such as `support-primary` instead of hard-coding provider model names throughout the product.

The repository already has important foundations:

- Contract C-4, Serviq's provider-neutral LLM request/response contract;
- OpenAI and Anthropic adapters;
- the deterministic fake adapter used by required tests;
- encrypted tenant BYOK secret storage;
- tenant-scoped provider-connection CRUD;
- `provider_connections` and `model_configurations` database tables;
- provider-management permission checks;
- architecture-defined provider-test route and rate-limit defaults.

However, the missing decisions are exactly the decisions these four builder tickets say **not** to invent.

## GitHub tracking created for this batch

| Linear ticket | GitHub issue | Ticket branch | Documentation PR | Current feature status |
|---|---:|---|---:|---|
| OPE-296 | #127 | `agent/ope-296-gemini-adapter` | #131 | Needs Architect Decision |
| OPE-297 | #128 | `agent/ope-297-openrouter-adapter` | #132 | Needs Architect Decision |
| OPE-298 | #129 | `agent/ope-298-provider-connectivity-test` | #133 | Needs Architect Decision |
| OPE-299 | #130 | `agent/ope-299-model-configuration-crud` | #134 | Needs Architect Decision |

All four documentation PRs passed the repository CI and Security workflows before being merged.

The feature issues remain open because the requested product behavior has not been completed. Closing those issues would falsely say the production feature exists.

---

# OPE-296 — Implement Gemini generation and streaming adapter

## What the feature is supposed to do

Serviq does not want the rest of the product to know how each AI provider works internally.

For example, an agent should not need code like:

> “If provider is Gemini, build this Google-specific object, call this Google-specific method, parse this Google-specific stream chunk, and catch this Google-specific exception.”

Instead, Serviq owns one internal language called **Contract C-4**. An agent sends a C-4 request. A provider adapter translates that request into the provider's language. The adapter then translates the result back into C-4.

OPE-296 is meant to create that translator for Gemini.

It must eventually support:

- normal non-streaming generation;
- streaming generation in order;
- Serviq system/user/assistant message semantics where Gemini supports them;
- output-token and timeout budgets;
- normalized token usage;
- normalized finish reason;
- request ID when Gemini exposes one safely;
- normalized authentication, rate-limit, timeout, unavailable, and invalid-request errors;
- explicit rejection when C-4 asks for something the chosen Gemini API cannot safely support.

The provider API key must remain server-side and Gemini SDK objects must not leak into agent or domain code.

## What was already available

The repository has:

- `services/llm-gateway/app/adapters/base.py`, which defines the adapter interface;
- `services/llm-gateway/app/schemas/c4.py`, which defines the provider-neutral contract;
- a deterministic fake adapter;
- real OpenAI and Anthropic adapters;
- exact OpenAI and Anthropic SDK versions frozen by ADR-011.

This gives Gemini a clear architectural home and examples of what a compliant adapter should look like.

## What blocked implementation

The repository does **not** have an architect-approved Gemini SDK or transport.

ADR-011 explicitly approves only:

- `openai==2.53.0`;
- `anthropic==0.121.0`.

The same ADR explicitly says it does not approve Gemini dependencies.

The LLM Gateway dependency manifest therefore contains no approved Gemini SDK.

OPE-296 itself says to stop with `Needs Architect Decision` if there is no approved Gemini SDK in repository context. The builder reached that exact condition.

## Why choosing an SDK inside OPE-296 would be wrong

A package choice may look like a small implementation detail, but it changes production behavior.

The chosen SDK determines things such as:

- supported Python versions;
- authentication setup;
- streaming interface;
- timeout behavior;
- retry behavior;
- exception classes;
- structured-output support;
- dependency tree and vulnerability surface;
- lockfile behavior;
- upgrade path.

If the feature ticket quietly selected a package, that package choice would become an architecture decision without review.

That would also defeat the purpose of ADR-011, which was created specifically so provider dependencies are reproducible and intentional.

## What was changed for OPE-296

A dedicated GitHub issue and branch were created.

The branch added:

`docs/architecture-blockers/OPE-296-gemini-sdk-decision.md`

That document records:

- what was inspected;
- the exact ADR-011 conflict;
- why no dependency was added;
- which architecture decisions are required to unblock the ticket;
- what was deliberately left unchanged.

PR #131 carried exactly that ticket-scoped documentation change. CI and Security passed, and the PR was squash-merged.

No Gemini adapter, dependency, network call, C-4 field, model-routing behavior, or secret-handling behavior was added.

## What this improves

The immediate improvement is **architectural safety and traceability**, not a new user feature.

A future engineer does not have to rediscover why Gemini is absent or guess whether the omission was accidental. The blocker is now version-controlled and connected to the ticket.

More importantly, Serviq avoids creating a provider-neutral gateway that is provider-neutral only in name. The transport decision will be explicit before provider-specific code enters the system.

## Exact decision needed before coding resumes

An architect-owned decision must freeze at least:

1. the approved Gemini SDK/package or explicitly approved alternative transport;
2. exact compatible version or version policy;
3. Python 3.14 compatibility expectation;
4. retry ownership;
5. timeout ownership;
6. dependency-locking/reproducibility behavior;
7. any C-4 capability that Gemini must explicitly reject rather than silently ignore.

Once that is merged, OPE-296 can resume as a normal provider-adapter implementation ticket.

---

# OPE-297 — Implement OpenRouter generation and streaming adapter

## What the feature is supposed to do

OpenRouter gives applications access to many upstream models through one provider service.

For Serviq, the important boundary is that tenant users may choose a saved OpenRouter credential and a validated upstream model, but they must **not** be able to turn Serviq into an arbitrary HTTP proxy.

OPE-297 is supposed to add an OpenRouter implementation behind Contract C-4 with:

- non-stream generation;
- ordered streaming;
- normalized text/structured output;
- normalized usage;
- normalized finish reason;
- safe request ID where available;
- timeout/output-token budgets;
- safe error mapping;
- no raw provider body, headers, exceptions, or key material outside the adapter.

The endpoint/base URL must be owned by Serviq configuration/code rather than caller input.

## What blocked implementation

The repository has no frozen OpenRouter transport/client choice.

There are several technically possible approaches. For example, OpenRouter exposes an OpenAI-compatible API, so one implementation might reuse the OpenAI SDK with a Serviq-owned OpenRouter base URL. Another implementation might use a direct HTTP client. Another might use a dedicated package.

But “technically possible” is not the same as “architecturally approved.”

ADR-011 explicitly says it does not approve OpenRouter dependencies, and no later architecture decision freezes the transport pattern.

OPE-297 explicitly says to stop when that choice is not frozen.

## Why the builder did not simply reuse the OpenAI SDK

Doing so would answer several security and maintenance questions without authorization:

- Is the OpenAI SDK officially Serviq's OpenRouter transport?
- Where is the OpenRouter base URL frozen?
- Can any caller override it?
- Which OpenRouter-specific headers can Serviq send?
- How should OpenRouter errors map when the OpenAI SDK wraps them?
- Does one OpenAI SDK upgrade now change two provider adapters?
- Which behavior belongs to OpenRouter versus the generic OpenAI-compatible transport?

The ticket intentionally requires these answers before implementation.

## What was changed for OPE-297

A dedicated GitHub issue and branch were created.

The branch added:

`docs/architecture-blockers/OPE-297-openrouter-transport-decision.md`

PR #132 contained only this blocker record, passed CI and Security, and was squash-merged.

No OpenRouter dependency, endpoint, adapter, header handling, C-4 change, or caller-controlled URL behavior was introduced.

## What this improves

The stop protects one of the most important provider-boundary rules: **tenants may select configured provider resources, not arbitrary destinations.**

That reduces the risk of accidental SSRF-like proxy behavior, hidden transport coupling, and provider-specific code escaping into shared layers.

It also gives a future implementation a clear decision checklist instead of making an engineer infer architecture from whatever code happened to be written first.

## Exact decision needed before coding resumes

An architect-owned change must freeze:

1. OpenRouter transport strategy;
2. exact dependency/version when a package is used;
3. immutable Serviq-owned base URL behavior;
4. prohibition on caller-controlled endpoint overrides;
5. timeout/retry ownership;
6. provider-specific header policy;
7. Python 3.14 and reproducibility expectations.

---

# OPE-298 — Implement provider connectivity test endpoint

## What the feature is supposed to do

A tenant administrator can already save a BYOK provider credential. Saving a value, however, does not prove that the credential is valid.

OPE-298 is intended to add:

```text
POST /api/v1/providers/{providerConnectionId}/test
```

A safe connectivity test is intentionally different from a normal AI-completion endpoint.

The user should **not** submit:

- a custom prompt;
- an arbitrary model string;
- an arbitrary URL;
- a custom provider body.

The server should construct one tiny, fixed request that is sufficient to prove the connection works.

The endpoint must also:

- resolve the provider connection only inside the current tenant;
- require provider-management capability;
- resolve the existing encrypted secret reference;
- select the adapter from the stored provider enum;
- use a short bounded timeout;
- enforce provider-test rate limits;
- store safe status metadata only;
- never persist or return raw provider responses, provider headers, SDK exceptions, or keys.

## What is already frozen

Architecture v1.3 already defines the route.

It also freezes two relevant default rate limits:

- `provider.test.user`: 10/minute per tenant user;
- `provider.test.connection`: 30/hour per provider connection.

The provider connection table also already defines the status vocabulary:

- `untested`;
- `active`;
- `invalid`;
- `disabled`.

## What blocked implementation

Two architecture rules needed by the ticket are missing.

### Missing decision 1: which model is used for the test?

The ticket requires an **architecture-approved minimal model-selection strategy**.

The repository does not currently freeze:

- a test model for each provider;
- whether provider testing requires a model configuration to exist first;
- whether the server owns a provider-specific test model list;
- how model retirement is handled.

Hard-coding a model inside the endpoint would create a hidden operational dependency and could stop working when a provider retires or changes access to that model.

### Missing decision 2: what happens to status on temporary failures?

Authentication failure can reasonably establish that the credential is invalid. But a 429, timeout, or provider outage does **not** prove the credential is invalid.

The ticket therefore requires architecture-approved transient failure semantics.

The database exposes possible statuses, but the Architecture does not currently say whether a transient failure should:

- preserve `active`;
- reset to `untested`;
- change to `invalid`;
- follow another rule.

That state affects the UI and later provider routing, so it must not be guessed.

### Dependency on OPE-296 and OPE-297

A complete provider test must work across the supported provider set. Gemini and OpenRouter adapters are themselves blocked by unresolved architecture decisions.

Shipping a test endpoint that only works for OpenAI and Anthropic would create inconsistent provider behavior and would not satisfy the intended MAS-2 scope.

## What was changed for OPE-298

A dedicated issue and branch were created.

The branch added:

`docs/architecture-blockers/OPE-298-provider-test-contract-decisions.md`

PR #133 documented the already-frozen route/rate limits, the missing model-selection/status rules, and the adapter dependencies. CI and Security passed before the PR was squash-merged.

No provider test route, external model call, rate limiter, secret resolution path, or provider status mutation was added.

## What this improves

This protects the reliability of provider status.

Without explicit rules, a temporary provider outage could make Serviq permanently label a valid credential as invalid. Or the system could mark a provider active merely because an arbitrary hard-coded model happened to respond.

The stop also prevents the provider-test endpoint from becoming an inexpensive path around normal model configuration and gateway controls.

## Exact decision needed before coding resumes

An architect-owned change must freeze:

1. provider-by-provider minimal model-selection strategy;
2. whether model configuration must exist before connectivity testing;
3. safe test-model ownership when no model configuration exists;
4. status transition for authentication failure;
5. status transition for 429, timeout, unavailable, and other transient failures;
6. stable `last_error_code` vocabulary for those outcomes;
7. the API-to-LLM-gateway call boundary while preserving the rule that external calls do not run inside DB transactions;
8. Gemini/OpenRouter adapter prerequisites.

---

# OPE-299 — Implement model configuration CRUD and alias validation

## What the feature is supposed to do

Provider model names change. Different providers also use different naming conventions.

Serviq therefore needs an internal stable abstraction.

Instead of an agent saying:

> “Use provider model string X.”

it should eventually say something like:

> “Use Serviq model configuration `support-primary`.”

The configuration can then point to a tenant's provider connection and its approved upstream model.

OPE-299 is meant to expose:

```text
GET    /api/v1/models
POST   /api/v1/models
PATCH  /api/v1/models/{modelConfigurationId}
DELETE /api/v1/models/{modelConfigurationId}
```

The existing database table already contains:

- tenant ID;
- provider connection ID;
- alias;
- upstream model;
- purpose;
- enabled flag.

The schema already enforces tenant-unique aliases and allowed purposes.

## What was already available

The provider/model metadata migration created `model_configurations` with:

- alias length 1..80;
- upstream model length 1..160;
- purpose `generation|embedding|rerank`;
- `UNIQUE(tenant_id, alias)`;
- restrictive provider-connection FK;
- indexes for tenant/purpose/enabled and provider connection.

Provider-management capability and tenant-scoped provider queries also already exist.

This is enough to see how basic CRUD could be built.

## What blocked implementation

The ticket requires more than basic CRUD.

Its delete behavior must return a conflict when a published agent/configuration or another frozen reference depends on a model configuration. Its required tests include the referenced-deletion case.

But the current repository has no implemented authoritative reference to `model_configurations`.

There is:

- no FK from an implemented table to a model configuration;
- no implemented `model_configuration_id` reference;
- no implemented agent-version persistence yet;
- no frozen agent `config` JSON field/path saying whether a model is referenced by UUID, alias, purpose mapping, or another structure.

So there is no trustworthy database/repository question the delete service can ask to determine whether the model is “in use.”

OPE-299 explicitly says to stop when model mutability/reference rules are not frozen or agent-version references are not implemented compatibly. That stop condition is currently true.

## Why partial CRUD was not shipped

It would be easy to add list/create/update/delete routes now and let delete succeed because nothing currently references the row.

That would be the wrong result.

It would create an API that appears complete but lacks one of the ticket's most important safety properties. Later, when published agents exist, deleting a model could leave them pointing at something that no longer exists.

The opposite shortcut would also be wrong: inventing an agent JSON structure or new FK from OPE-299 would silently change a different module's contract.

## What was changed for OPE-299

A dedicated issue and branch were created.

The branch added:

`docs/architecture-blockers/OPE-299-model-reference-rules.md`

PR #134 documents the frozen model table, the missing authoritative reference source, why partial CRUD was rejected, and the decisions required before implementation. CI and Security passed, and the PR was squash-merged.

No model CRUD route, schema, service, repository query, migration, model row, or agent configuration behavior was added.

## What this improves

This protects **configuration referential integrity** at the product level.

A normal database foreign key protects relationships that are represented relationally. It cannot protect a model alias or UUID hidden inside an undefined future JSON configuration. The project needs to decide that reference format before it can truthfully promise safe deletion.

Stopping now avoids a future migration from “model aliases are editable/deletable freely” to “published agents depend on them and now we need emergency compatibility rules.”

## Exact decision needed before coding resumes

An architect-owned change must freeze:

1. how agent versions reference models;
2. whether the authoritative identity is model configuration UUID, alias, or another object;
3. which draft/published/deployed references block deletion;
4. which model fields remain mutable after a reference exists;
5. conflict semantics for referenced deletion;
6. authoritative reference-check implementation;
7. provider-status eligibility for create/update beyond the ticket's minimum “not disabled” rule if stricter behavior is desired.

---

# What was deliberately not done

For all four tickets, the builder did **not**:

- add an unapproved dependency;
- change Contract C-4;
- invent new database columns or agent configuration fields;
- create provider-specific endpoints outside the gateway;
- add arbitrary URL support;
- create a partial endpoint and call it complete;
- weaken an acceptance test to fit current code;
- close the Linear tickets;
- close GitHub issues #127–#130.

Those are important non-actions. They keep the implementation aligned with the project's rule that builder tickets consume frozen contracts rather than redefining them.

---

# Validation performed

Each ticket received a separate branch and documentation PR:

- #131 for OPE-296;
- #132 for OPE-297;
- #133 for OPE-298;
- #134 for OPE-299.

Every one of those PRs passed both the repository CI workflow and the Security workflow before merge.

Because no production feature code was introduced, the correct claim is **not** that provider/model feature tests passed. The correct claim is that the repository remained green after adding the auditable blocker records.

---

# Recommended unblock sequence

The safest order is:

1. **Architect decision for provider transports/dependencies.** Freeze Gemini SDK and OpenRouter transport.
2. **Resume OPE-296 and OPE-297.** Implement and validate both adapters behind unchanged C-4.
3. **Architect decision for provider connectivity testing.** Freeze minimal model selection and transient status semantics.
4. **Resume OPE-298.** Implement the bounded connectivity test using all supported adapters.
5. **Architect decision for model-reference semantics.** Freeze how agent versions reference model configurations and what blocks deletion/mutation.
6. **Resume OPE-299.** Implement complete CRUD with real reference protection.

This order avoids circular assumptions and prevents later tickets from forcing earlier contracts retroactively.

---

# Current status at the end of this batch

The following **work is completed**:

- GitHub issues #127–#130 were created separately from their Linear tickets.
- Four separate ticket branches were created.
- The repository, architecture, provider adapters, database schema, and prior ADRs were audited.
- All four ticket stop conditions were identified with concrete evidence.
- Each Linear ticket has a detailed blocker comment.
- Each GitHub issue has a visible `Needs Architect Decision` implementation-status section.
- Four ticket-specific architecture-blocker documents were committed through separate PRs.
- PRs #131–#134 passed CI and Security and were merged.
- This batch implementation/status guide was created.
- `docs/SERVIQ_BUILD_GUIDE.md` is updated separately with the cumulative reconciliation.

The following **product features are not completed**:

- Gemini generation/streaming adapter;
- OpenRouter generation/streaming adapter;
- provider connectivity test endpoint;
- model configuration CRUD and safe reference-aware deletion.

Those features must remain open until their architecture prerequisites are approved and their actual acceptance tests pass.

---

# OPE-299 current status correction — implementation resumed and completed

The earlier OPE-299 blocker section remains an accurate historical explanation of why the first implementation attempt stopped. It is no longer the current feature status.

On 2026-08-19, the missing model reference and mutability rules were frozen in `docs/architecture-decisions/ADR-015-model-configuration-reference-and-mutation-semantics.md`.

OPE-299 then resumed on branch `ope299`. The implementation added the frozen model CRUD routes, active-provider eligibility, tenant isolation, immutable alias/purpose semantics, the tenant-safe `model_configuration_references` registry, deterministic alias conflicts, reference-aware deletion, and real PostgreSQL integration tests.

Runtime PR #145 was merged only after exact head `0fc1bfd0922175193e3857afb6a16cb6ea0e91ed` passed CI #236 and Security #212.

The older statement that model configuration CRUD is blocked should therefore be read as historical context, not as the current state of OPE-299.
