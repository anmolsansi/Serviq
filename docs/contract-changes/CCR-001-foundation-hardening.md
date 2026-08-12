# Contract Change Record: CCR-001 — Foundation Hardening

**Status:** Applied  
**Date:** 2026-08-13  
**Architect-owned artifacts updated:** `docs/ARCHITECTURE.md` v1.2  
**Code impact:** None. No production implementation tickets or scaffolded contracts exist yet.

This record closes six contract gaps found during the Premium Product Builder verification of the initial Serviq documentation.

## Change 1 — Organization invitation persistence and lifecycle

**Contract:** MAS-1 workforce invitation API and database schema.

**Current shape:**

- API exposed `POST /api/v1/organizations/{organizationId}/invitations`.
- No exact invitation persistence model existed.
- Acceptance, revocation, token storage, expiry, and role assignment were not frozen.

**New shape:**

Database adds:

```text
organization_invitations
organization_invitation_roles
```

Invitation records store normalized email, one-way token hash, status, inviter, accepted user, expiry, accepted/revoked timestamps, and requested role IDs through the join table. Plaintext invitation tokens are never persisted.

API is frozen as:

```text
GET    /api/v1/organizations/{organizationId}/invitations
POST   /api/v1/organizations/{organizationId}/invitations
DELETE /api/v1/organizations/{organizationId}/invitations/{invitationId}
POST   /api/v1/invitations/accept
```

Create returns an `inviteUrl` once. Invitation default expiry is 7 days. Acceptance requires an authenticated workforce identity whose normalized verified email matches the invitation.

**Reason:** The existing invitation endpoint could not be implemented safely without a persistence and token lifecycle decision.

**Breaking?** No. No implementation exists. This is an additive freeze of an incomplete contract.

**Compatibility plan:** Not required before code exists.

**Migration plan:** Initial MAS-1 schema migration creates both invitation tables and the partial unique pending-invite index.

**Downstream impact:**

- MAS-1 implementation tickets must use the frozen invitation tables/endpoints.
- MAS-10 Team & Access UI must list pending invitations and handle one-time invite URL creation.
- MAS-11 audit must record invite created, revoked, accepted, and failed acceptance decisions.

## Change 2 — Feature flag and rate-limit storage ownership

**Contract:** MAS-12 platform configuration persistence and runtime consumption.

**Current shape:**

Platform APIs existed for feature flags and rate limits, but the authoritative persistence layer was not specified.

**New shape:**

PostgreSQL is authoritative through:

```text
platform_feature_flags
rate_limit_policies
```

Valkey is a derived runtime cache with a maximum 60-second TTL and explicit invalidation after updates. Runtime rate counters remain in Valkey. Missing/invalid configuration falls back to frozen built-in defaults, never unlimited access.

**Reason:** Builders must not decide where operational policy lives, and a cache must not become the only source of configuration truth.

**Breaking?** No. No implementation exists.

**Compatibility plan:** N/A.

**Migration plan:** Initial MAS-12 migration creates both tables. Seed migration inserts frozen V1 defaults from Architecture Section 5.4.

**Downstream impact:** MAS-12, MAS-13 rate-limit/security tests, API gateway middleware, observability.

## Change 3 — Customer external reference uniqueness

**Contract:** `customers` database uniqueness.

**Current shape:**

```text
UNIQUE NULLS NOT DISTINCT(tenant_id, external_ref)
```

This incorrectly makes multiple `NULL` external references conflict within one tenant.

**New shape:**

```text
Partial unique index: UNIQUE(tenant_id, external_ref)
WHERE external_ref IS NOT NULL
```

**Reason:** Multiple customers may legitimately exist before or without an external system reference, while non-null external references must remain unique per tenant.

**Breaking?** No. No database exists yet.

**Compatibility plan:** N/A.

**Migration plan:** Initial customer migration creates only the partial unique index. Builders must not create the previous `NULLS NOT DISTINCT` constraint.

**Downstream impact:** MAS-1/5/7 customer persistence and tenant-isolation tests.

## Change 4 — Frozen rate-limit and agent-budget defaults

**Contract:** Platform operational limits and MAS-6 run controls.

**Current shape:**

The architecture required limits and budgets but left actual values to implementation.

**New shape:**

Architecture Section 3.4 freezes agent defaults and hard ceilings, including:

- 12 default / 20 hard maximum agent steps;
- 4 default / 8 hard maximum model calls;
- 3 default / 6 hard maximum retrieval calls;
- 4 default / 8 hard maximum tool calls;
- 1 default mutating execution per run, hard maximum 2 with independent policy authorization;
- 45-second default interactive wall-clock budget, 90-second hard maximum;
- 20-second model request timeout;
- 10-second read tool timeout and 20-second mutation timeout;
- 32k aggregate model-input default and 1,500 output-token default per call;
- bounded provider/tool retry rules.

Architecture Section 5.4 freezes route-group defaults for login, customer messages/conversation creation, provider tests/calls, knowledge ingestion, evaluation, privacy requests, webhook configuration, and platform controls.

**Reason:** Rate limits and run budgets are security, reliability, cost, and UX contracts. Builders must not invent them.

**Breaking?** No. No implementation exists.

**Compatibility plan:** Future adjustments use MAS-12 configuration when within hard limits. Hard-limit changes require a new CCR.

**Migration plan:** Seed `rate_limit_policies` with current defaults. Agent version schema validates configured budgets against hard limits.

**Downstream impact:** MAS-2, MAS-3, MAS-5, MAS-6, MAS-10, MAS-12, MAS-13.

## Change 5 — Privacy retention, export, deletion, and backup behavior

**Contract:** Customer-data lifecycle and privacy APIs.

**Current shape:**

The prior architecture mentioned retention/deletion/export but did not define exact V1 periods, deletion semantics, or backup behavior.

**New shape:**

Architecture Section 4.5 freezes retention by data class and adds:

```text
data_subject_requests
```

API adds:

```text
POST /api/v1/customer/privacy/export
POST /api/v1/customer/privacy/delete
GET  /api/v1/customer/privacy/requests/{requestId}
```

Key lifecycle rules:

- conversation content: 90 days after resolution;
- agent/retrieval/tool customer-bearing execution detail: generally 30 days;
- support handoff/internal notes: 180 days;
- analytics/audit operational records: 400 days, with audit pseudonymization after customer deletion;
- logs: 30 days; traces: 7 days; metrics: 90 days;
- exports: artifact max 7 days, signed URL max 24 hours;
- export/delete completion target: 7 days after verification;
- immutable production backups: maximum 30-day retention; any restore must replay deletion requests before restored data is exposed.

**Reason:** Privacy behavior must be implementable and testable rather than an undefined future policy.

**Breaking?** No. Additive V1 contract.

**Compatibility plan:** Longer or jurisdiction-specific retention requires a future Product/Architect decision. No builder may silently change these defaults.

**Migration plan:** Create `data_subject_requests`; add `customers.deleted_at`, `customers.status=deleted`, and `conversations.resolved_at` as defined in Architecture v1.2.

**Downstream impact:** MAS-5, MAS-7, MAS-9, MAS-11, MAS-13, object-storage lifecycle, observability lifecycle, runbooks.

## Change 6 — Outbound webhook SSRF and DNS-rebinding protection

**Contract:** Outbound tenant webhook destination validation and delivery.

**Current shape:**

Webhook HMAC and retry behavior existed, but tenant-controlled destination URLs did not have the same network-boundary protection as knowledge crawling.

**New shape:**

Production V1 webhook egress requires:

- HTTPS only;
- port 443 only;
- reject URL credentials and fragments;
- reject loopback, private, link-local, CGNAT, metadata, multicast, reserved, and non-routable IPv4/IPv6 targets;
- DNS resolution at endpoint validation and again immediately before every delivery attempt;
- connected peer IP must match an allowed result of the current resolution;
- redirects disabled;
- 5-second connect timeout, 10-second total timeout;
- response-body read cap of 64 KiB;
- explicit local-only Docker development allowlist exception that is invalid outside `SERVIQ_ENV=local`;
- premium security review for URL validation, egress, and HMAC implementation.

**Reason:** A tenant-controlled webhook URL is an SSRF surface and must not reach internal infrastructure or cloud metadata services.

**Breaking?** No. No implementation exists.

**Compatibility plan:** Additional production ports or private-network webhooks require a new architecture/security contract.

**Migration plan:** `webhook_endpoints` includes `last_validated_at`. Existing production endpoint migration is not needed because no production data exists.

**Downstream impact:** webhook configuration UI, webhook worker, network/security tests, local Compose config, MAS-11 delivery analytics, MAS-13 security tests.

## Updated Artifacts

- [x] `docs/ARCHITECTURE.md` updated to v1.2.
- [x] This CCR added.
- [ ] Affected implementation tickets: none exist yet.
- [ ] `docs/repo_context.md`: not created yet because repository scaffolding/audit has not occurred. When created, it must reflect Architecture v1.2.

## Review Requirement

Before the corresponding code merges, premium review is mandatory for invitation token handling, rate limiting, privacy deletion, webhook egress/SSRF controls, auth/tenant isolation, and any migration that alters these contracts.
