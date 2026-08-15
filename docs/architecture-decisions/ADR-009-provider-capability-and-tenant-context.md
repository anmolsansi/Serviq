# ADR-009 — Provider capability and trusted tenant context

## Status

Accepted for OPE-291.

## Context

The PRD freezes provider-credential management to Tenant Owner, Tenant Administrator, and AI Configuration Manager. The current executable RBAC seed contains Owner and Admin plus organization-settings/member-management capability keys, but no provider-specific capability and no complete AI Manager role bootstrap yet.

The frozen provider routes are `/api/v1/providers` rather than organization-ID routes. Architecture also says Phase 1 MAS-2 Provider/BYOK is built against mocked tenant context and explicitly states that no client-supplied tenant ID is authorization.

## Decision

1. Introduce the dedicated capability key `ai.providers.manage` and grant it to the existing global Owner/Admin workforce roles in a reversible migration.
2. Provider read and mutation routes require this capability in V1. The future complete AI Configuration Manager role must receive the same capability when that role is bootstrapped; OPE-291 does not create a partial AI Manager role whose other PRD permissions would be missing.
3. Provider routes obtain tenant identity only from trusted server-owned request state through `require_tenant_id`. They do not accept a tenant ID in JSON, query parameters, or a client-trusted header.
4. Until the organization-switch/tenant-context boundary is implemented, production requests without server-owned tenant context fail closed. Integration tests override the dependency with explicit tenant A/B values, matching Architecture's Phase 1 mocked-tenant-context allowance.

## Why not reuse `organization.settings.write`?

The PRD says AI Configuration Manager may manage provider credentials but may not edit organization settings. Reusing `organization.settings.write` would permanently couple two permissions that the product explicitly separates.

## Why not create AI Manager here?

A partial AI Manager with only provider access would misrepresent the PRD because AI Manager must also configure/publish agents, tools/policies, and view analytics. Role bootstrap should be complete and internally consistent rather than introduced piecemeal by a provider CRUD ticket.

## Security consequence

Provider authorization remains capability-based and server-side. Tenant selection cannot be forged by placing another tenant UUID in the provider request. Missing trusted context is authentication/authorization failure, not a fallback to a default tenant.
