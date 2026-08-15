# OPE-291 — BYOK provider connection CRUD security review

## Scope

This review covers tenant-scoped provider connection list/create/read/update/delete behavior, the handoff between relational provider metadata and the `TenantSecretStore`, provider authorization, key replacement, and deletion. It does not implement connectivity testing, model alias CRUD, LLM routing, or provider SDK calls.

## Assets at risk

- Tenant provider API keys.
- Opaque `secret_ref` values linking relational metadata to encrypted secret storage.
- Provider connection metadata.
- Tenant isolation.
- Provider-management authorization.
- Model configurations that reference a provider connection.

## Trusted tenant context

The frozen routes do not contain an organization ID. OPE-291 therefore requires a server-owned `serviq_tenant_id` request-state value through `require_tenant_id`. No provider request accepts tenant ID in JSON or query parameters, and the service never derives tenant identity from provider metadata supplied by the caller.

This is intentionally fail closed. Until Serviq's organization-switch/tenant-context middleware is implemented, ordinary production requests without trusted tenant context cannot use these routes. Integration tests override the dependency explicitly, which matches the Architecture's Phase 1 instruction to build MAS-2 Provider/BYOK against mocked tenant context.

## Capability authorization

Provider routes require `ai.providers.manage` after resolving the caller's active membership for the trusted tenant. OPE-291 adds that dedicated capability to the existing global Owner/Admin system roles because the PRD explicitly permits both to manage provider credentials.

The implementation does not reuse `organization.settings.write`, because the PRD permits AI Configuration Manager to manage providers while forbidding organization-settings edits. A future complete AI Configuration Manager role must receive `ai.providers.manage` as part of its full role bootstrap rather than being introduced here as a misleading partial role.

A caller who has no membership in the trusted tenant receives the non-disclosing provider-not-found path. A tenant member without the provider capability receives `403 FORBIDDEN`.

## Plaintext API-key lifetime

Create/PATCH schemas use Pydantic `SecretStr` for `apiKey`. The service passes the secret directly into the `TenantSecretStore`. Relational persistence receives only the opaque `secret_ref` returned by that adapter.

Provider response schemas contain no `apiKey`, `secretRef`, ciphertext, bootstrap key, or encryption metadata. Integration tests assert representative fake key material is absent from responses, persisted relational values, encrypted-file plaintext, and captured logs.

Python cannot guarantee memory zeroization of strings. The implementation therefore minimizes plaintext handling rather than claiming impossible zeroization.

## Cross-store create compensation

Creating a provider spans two persistence systems:

1. encrypted secret store;
2. PostgreSQL provider metadata.

The caller is authorized before any secret is written. The secret is then written first so PostgreSQL never commits a metadata row pointing at a secret that was never created.

If the metadata transaction fails, including tenant-local display-name uniqueness, the just-created secret is deleted. The failure test verifies the secret record count returns to its pre-attempt value.

If compensation itself fails, the service surfaces `PROVIDER_SECRET_CLEANUP_FAILED` instead of hiding an orphaned secret. An orphan is undesirable but is safer than a live relational row pointing to missing credential material.

## Key replacement compensation and concurrency

For PATCH with a new API key:

1. authorization/existence preflight completes;
2. a new secret is written under a new opaque ref;
3. the provider row is selected with PostgreSQL `FOR UPDATE`;
4. **only after that lock is held**, the current `secret_ref` is captured as the predecessor;
5. metadata switches atomically to the new ref and resets connection status to `untested`, clearing previous test timestamp/error state;
6. after PostgreSQL commit, the exact locked predecessor secret is deleted.

Capturing the old ref only under the row lock prevents two simultaneous rotations from deleting a stale predecessor selected before another rotation committed.

If the PostgreSQL update fails, only the newly created secret is cleaned up and the currently referenced old secret remains intact. The integration test verifies a display-name conflict during key replacement leaves the old key retrievable.

If post-commit deletion of the old secret fails unexpectedly, the metadata already points to the valid new secret and no application lookup references the old material. The service surfaces a cleanup error for operational attention rather than rolling metadata back to a potentially stale key.

## Delete ordering

Delete selects the tenant-scoped provider row with `FOR UPDATE` and checks model references inside the same transaction. If any model configuration still references the provider, deletion returns conflict and neither metadata nor secret is removed.

When no reference exists, PostgreSQL metadata is removed first. The secret is then deleted. This order intentionally prefers a harmless orphaned encrypted secret over a live model/provider reference whose credential has already disappeared. Unexpected secret-cleanup failure is surfaced explicitly.

## Tenant isolation

Every provider repository operation includes `tenant_id`. Known provider UUIDs from tenant B return not-found while operating under tenant A. Tenant-local display-name uniqueness allows two tenants to use the same human-facing provider name without collision.

The integration test creates two tenants, inserts overlapping provider display names, confirms tenant A lists only its provider, and confirms a known tenant-B provider UUID is hidden.

## Model-reference safety

`DELETE /api/v1/providers/{id}` checks `model_configurations` using both tenant ID and provider connection ID. A referenced provider cannot be deleted. This avoids leaving model configuration rows whose gateway credential source disappeared.

## Input hardening

Provider create/update models reject unknown fields. Supported provider values are frozen to `openai`, `anthropic`, `gemini`, and `openrouter`. Display names are length-bounded and stripped. An empty PATCH is rejected. The provider kind is intentionally immutable in this ticket because changing provider family while retaining model/connection identity would make downstream compatibility ambiguous.

## Review conclusion

OPE-291 keeps provider key material out of relational storage and API responses, uses dedicated capability authorization and server-owned tenant context, compensates cross-store failures, serializes key replacement at the provider row, preserves referenced providers, and exercises tenant isolation and secret redaction against real PostgreSQL plus the encrypted local secret adapter.