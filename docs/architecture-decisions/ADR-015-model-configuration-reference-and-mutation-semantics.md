# ADR-015 — Model configuration reference and mutation semantics for OPE-299

## Status

Accepted.

## Context

OPE-299 implements the frozen tenant-facing model catalog routes:

```text
GET    /api/v1/models
POST   /api/v1/models
PATCH  /api/v1/models/{modelConfigurationId}
DELETE /api/v1/models/{modelConfigurationId}
```

The `model_configurations` table already stores the tenant, provider connection, stable alias, upstream provider model string, purpose, enabled flag, and timestamps. The table also already enforces tenant-unique aliases and the frozen `generation|embedding|rerank` purpose vocabulary.

The original OPE-299 implementation correctly stopped because the repository had no authoritative way to answer whether a model configuration was referenced by production configuration. The planned `agent_versions.config` JSON shape was not yet implemented or frozen deeply enough to make DELETE inspect a specific JSON path safely.

This ADR resolves that blocker without changing the future agent JSON schema and without coupling the model-management module to agent persistence details.

## Decision summary

Serviq will use the following rules:

- a model configuration is identified authoritatively by its UUID;
- `alias` is a stable tenant-facing name and is immutable after creation;
- `purpose` is immutable after creation because changing generation to embedding/rerank changes the semantic contract of the alias;
- `provider_connection_id`, `upstream_model`, and `enabled` are the PATCH-mutable fields;
- creating a model configuration requires a same-tenant provider connection whose current status is `active`;
- changing the provider connection, changing the upstream model, or enabling a model requires the target provider connection to be `active`;
- disabling an existing model remains allowed even when its provider is no longer active, so administrators can fail safe;
- foreign-tenant provider/model identifiers are non-disclosing and behave as not found;
- model responses never expose `secret_ref`, API keys, provider response bodies, or provider SDK types;
- duplicate aliases inside one tenant return conflict, while the same alias in another tenant is valid;
- deletion is blocked by an explicit model-reference registry rather than by parsing another module's JSON.

## Authoritative blocking-reference registry

OPE-299 adds the internal table:

```text
model_configuration_references
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  model_configuration_id uuid NOT NULL FK model_configurations RESTRICT
  reference_kind text NOT NULL CHECK length 1..80
  reference_id uuid NOT NULL
  created_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(tenant_id, model_configuration_id, reference_kind, reference_id)
Indexes: (tenant_id, model_configuration_id)
```

This table contains only references that must block deletion.

The UUID in `reference_id` is intentionally not a generic foreign key. The owning domain module remains responsible for its own relational/JSON contract and must insert/delete the corresponding registry row in the same database transaction in which a blocking production reference becomes active/inactive.

Examples of future owners include published agent versions or another architecture-approved production configuration. OPE-299 does not invent those modules' JSON paths, status transitions, or public schemas.

The model-management service asks one authoritative question before DELETE:

```text
Does this tenant/model UUID have at least one row in model_configuration_references?
```

If yes, deletion returns conflict. If no, the row may be deleted subject to normal authorization and database constraints.

This design keeps reference protection relational and queryable while allowing future modules to choose their own internal representation.

## Model identity and alias semantics

The model configuration UUID is the durable internal identity.

The alias is the stable human/admin-facing name used to decouple later agent/domain code from raw provider model strings. Allowing rename through PATCH would weaken that guarantee and make logs, configuration reviews, and future alias-based references ambiguous. Alias therefore cannot be changed by OPE-299 PATCH.

A future explicit rename workflow would require separate architecture because it would need impact analysis and possibly reference migration.

## Purpose semantics

Purpose is exactly one of:

```text
generation
embedding
rerank
```

Purpose is immutable after creation. A configuration named `support-primary` changing from generation to embedding is not a routine edit. It changes what downstream code is allowed to do with the configuration.

Changing purpose therefore requires creating a new model configuration and intentionally migrating callers.

## Mutable fields

PATCH accepts only:

```text
providerConnectionId
upstreamModel
enabled
```

At least one field must be supplied. Unknown fields, including `alias` and `purpose`, are rejected by the request schema.

`providerConnectionId` and `upstreamModel` may be changed together or independently. `enabled` may be toggled independently.

## Provider eligibility

A model configuration may only be created against a provider connection with:

```text
status = active
```

This is stricter than merely rejecting `disabled`, and it matches OPE-299's goal that aliases reference an active provider connection. OPE-298 now provides the explicit connectivity-test path that transitions a usable credential to `active`.

PATCH uses these rules:

- assigning a provider connection requires that target connection to be same-tenant and `active`;
- changing `upstreamModel` requires the currently selected/target provider to be `active`;
- setting `enabled=true` requires the currently selected/target provider to be `active`;
- setting `enabled=false` is allowed even if the existing provider is `untested`, `invalid`, or `disabled` so an administrator can disable an unsafe configuration.

The API does not automatically delete or rewrite model configurations when a provider later becomes invalid or disabled.

## Tenant isolation and non-disclosure

Every model lookup includes both:

- current tenant ID; and
- model configuration ID.

Every provider lookup used by model CRUD includes both:

- current tenant ID; and
- provider connection ID.

A foreign provider/model UUID returns the same public not-found behavior as a nonexistent UUID. This prevents callers from probing cross-tenant resource existence.

## Authorization

OPE-299 reuses the existing frozen provider-management capability:

```text
ai.providers.manage
```

The same capability already protects provider connection configuration, and model aliases are part of that same tenant AI-provider control plane.

## Validation

Create validates:

- `alias`: trim first, then 1..80 characters;
- `upstreamModel`: trim first, then 1..160 characters;
- `purpose`: exact frozen enum;
- `enabled`: boolean;
- `providerConnectionId`: UUID resolved only inside current tenant;
- unknown fields: rejected.

PATCH validates the mutable subset with the same upstream-model and boolean rules and rejects an empty patch.

Database constraints remain defense in depth. The service also catches uniqueness races and maps tenant alias collisions to a deterministic 409 rather than exposing database error text.

## Delete conflict behavior

If a blocking reference exists, DELETE returns HTTP 409 with stable Serviq code:

```text
MODEL_CONFIGURATION_IN_USE
```

The response does not reveal which private agent/configuration references the model. The existence of an in-tenant blocking reference is enough to explain that deletion cannot proceed safely.

An unreferenced model returns HTTP 204 and is deleted without cascading into provider connections or unrelated production configuration.

## Response projection

Model responses contain only:

```text
id
providerConnectionId
alias
upstreamModel
purpose
enabled
createdAt
updatedAt
```

They do not contain provider credentials, `secret_ref`, provider test internals, SDK objects, or arbitrary provider response data.

## Concurrency

PATCH and DELETE lock the target model row before mutation/deletion.

The database tenant-alias unique constraint remains the final arbiter for concurrent creates. Integrity errors caused by duplicate aliases are converted to stable conflict behavior.

Reference-owning future modules must create/remove registry rows transactionally with the state change that makes the reference blocking/non-blocking. The model DELETE transaction checks the registry while holding the model row lock, preventing normal application paths from deleting a model after the registry has established a blocking reference.

## Testing requirements

OPE-299 must cover at least:

- generation alias create;
- embedding and rerank create;
- duplicate same-tenant alias returns 409;
- same alias in another tenant is allowed;
- alias blank/too long rejected after normalization;
- upstream model blank/too long rejected after normalization;
- invalid purpose rejected;
- foreign provider rejected without disclosure;
- inactive/disabled provider rejected for create or safety-sensitive update;
- tenant list excludes foreign rows;
- authorized PATCH of mutable fields;
- alias/purpose PATCH rejected as unknown fields;
- unauthorized PATCH/DELETE denied;
- referenced DELETE returns 409;
- unreferenced DELETE returns 204;
- model responses contain no provider secret material.

## Scope exclusions

OPE-299 does not implement:

- provider API-key creation/rotation;
- provider connectivity testing;
- model fallback/routing chains;
- agent configuration schema;
- agent publish/deploy behavior;
- provider SDK selection;
- automatic model migration;
- alias rename workflow;
- purpose mutation workflow.

## Result

The original OPE-299 stop condition is resolved by making model UUID identity, mutation rules, provider eligibility, and blocking-reference ownership explicit. The CRUD implementation can now proceed without inventing the future agent JSON schema and without allowing unsafe deletion of registered production references.
