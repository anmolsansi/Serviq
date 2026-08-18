# OPE-299 — Model configuration CRUD architecture blocker

## Status

**Resolved by ADR-015 and implemented on branch `ope299`.**

The original OPE-299 audit correctly stopped because the repository had no authoritative way to determine whether a production configuration referenced a model configuration. At that point there was no implemented agent-version reference, no frozen model-reference JSON path, and no relational reference source that DELETE could query safely.

## Original blocker

OPE-299 requires deletion to return conflict when a published agent/configuration or another frozen production reference depends on a model configuration. The original repository state had no table or foreign-key column referencing `model_configurations`, so implementing DELETE as if every model were unreferenced would have falsely claimed the ticket was complete.

The ticket also required frozen mutation semantics. The repository did not yet say which fields remained safe to edit once future production configuration referenced a model.

## Resolution

`docs/architecture-decisions/ADR-015-model-configuration-reference-and-mutation-semantics.md` now freezes the missing contract without inventing the future agent JSON schema.

The accepted rules are:

- model configuration UUID is the authoritative internal identity;
- `alias` and `purpose` are immutable after creation;
- `providerConnectionId`, `upstreamModel`, and `enabled` are the only PATCH-mutable fields;
- create and safety-sensitive updates require a same-tenant `active` provider connection;
- disabling remains allowed as a fail-safe even if the existing provider later becomes inactive;
- blocking production references are registered in `model_configuration_references`;
- the reference registry uses tenant + model UUID as a database-enforced pair;
- referenced DELETE returns `409 MODEL_CONFIGURATION_IN_USE`;
- unreferenced DELETE returns 204;
- future agent/configuration modules own their own schemas and register/remove blocking references transactionally when their lifecycle requires it.

## Why the reference registry was chosen

The registry gives model management a real relational question to ask without parsing another module's JSON:

```text
Does this tenant/model UUID have any blocking model_configuration_references row?
```

That means OPE-299 can protect deletion now while future agent-version work remains free to define its own internal config shape through its own architecture process.

## Product impact

Serviq can now expose a stable tenant model catalog without coupling agents to raw provider model strings or provider credentials. The delete safety property is real rather than a placeholder, and the model alias remains stable because routine PATCH cannot rename it or change its semantic purpose.

## Implementation scope

The `ope299` branch implements:

- `GET /api/v1/models`;
- `POST /api/v1/models`;
- `PATCH /api/v1/models/{modelConfigurationId}`;
- `DELETE /api/v1/models/{modelConfigurationId}`;
- strict trimmed alias/upstream-model validation;
- exact `generation|embedding|rerank` purpose validation;
- tenant-scoped alias uniqueness;
- same-tenant active-provider eligibility checks;
- credential-free response projections;
- capability authorization using `ai.providers.manage`;
- non-disclosing foreign resource handling;
- reference-aware deletion;
- real PostgreSQL integration tests for CRUD, authorization, validation, tenant isolation, and deletion protection.

The future agent configuration schema, provider credentials, provider connectivity behavior, and model fallback/routing remain outside OPE-299.
