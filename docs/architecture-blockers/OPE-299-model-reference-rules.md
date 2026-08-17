# OPE-299 — Model configuration CRUD architecture blocker

## Status

**Needs Architect Decision.** The CRUD implementation was intentionally stopped because the required reference-protection behavior is not frozen in the current repository.

## What OPE-299 is trying to build

OPE-299 is meant to give each tenant a stable model catalog so future agent/domain code can use a Serviq model alias/configuration rather than importing raw provider model strings.

The frozen route surface is:

```text
GET    /api/v1/models
POST   /api/v1/models
PATCH  /api/v1/models/{modelConfigurationId}
DELETE /api/v1/models/{modelConfigurationId}
```

The existing database table already stores tenant ID, provider connection ID, alias, upstream model, purpose, and enabled state.

## What is already frozen

The current schema establishes:

- tenant-scoped model rows;
- `UNIQUE(tenant_id, alias)`;
- alias length 1..80;
- upstream model length 1..160;
- purpose exactly `generation|embedding|rerank`;
- a restrictive foreign key from model configuration to provider connection;
- an `enabled` flag.

Those facts are sufficient for basic validation, but not for the complete ticket.

## Blocking fact: reference protection has no authoritative source

The ticket requires deletion to return a conflict when a published agent/configuration or another frozen reference depends on the model configuration. The required automated tests explicitly include "Delete referenced model returns conflict."

The current migrated database has no table or foreign-key column referencing `model_configurations`. Repository search also found no implemented `model_configuration_id` reference.

Architecture plans an `agent_versions.config jsonb` field, but there is no implemented agent-version table yet and no frozen JSON schema/path specifying whether an agent references a model by:

- model configuration UUID;
- alias;
- purpose-specific alias;
- another routing structure.

Therefore there is currently no authoritative query that can answer "is this model referenced?"

## Why a partial CRUD implementation was not shipped

Shipping list/create/update and a delete that always succeeds when the database has no FK reference would falsely claim OPE-299 is complete and would make future published-agent protection a breaking retrofit.

Inventing a JSON path or new relational reference would be worse: it would silently change the frozen agent/configuration contract from a builder ticket.

OPE-299 explicitly says to stop if model mutability/reference rules are not frozen or agent-version references are implemented differently. The current repository satisfies that stop condition.

## Decision required to unblock OPE-299

An architect-approved change must freeze:

1. how agent versions and any other production configuration reference a model configuration;
2. whether the authoritative reference is a model-configuration UUID, alias, or another structure;
3. which references block deletion and whether draft versus published references differ;
4. which model fields remain mutable once referenced;
5. the exact conflict behavior when a reference exists;
6. whether disabled/invalid/untested provider connections may be used when creating or moving a model configuration, beyond the ticket's minimum "not disabled" rule.

After that decision is merged, the API can implement tenant-scoped CRUD, deterministic duplicate-alias handling, safe provider validation, and real deletion-reference tests without guessing.

## Product impact

The stop protects stable agent configuration. Model aliases exist specifically so future agents do not depend on provider strings. If their identity and deletion semantics are ambiguous now, a later agent publish workflow could point to a model that administrators can accidentally delete or mutate incompatibly. Freezing the reference contract first prevents that class of production configuration breakage.

## What changed in this branch

Only this architecture-blocker record was added. No API route, schema, repository query, database migration, provider validation, model row, agent configuration, or deletion behavior was changed.
