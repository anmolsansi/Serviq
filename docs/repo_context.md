# Serviq Repository Context

> Current-state engineering map. The knowledge-upload consistency state was
> refreshed on 2026-08-26 after V1.3.04A merged to `main` as `ae9c2d6`.
> This describes code that exists. Future contracts remain in `PRD.md`,
> `ARCHITECTURE.md`, and the staged roadmap. Earlier subsystem evidence notes
> retain their ticket-specific dates and commit references below.

## Executive snapshot

Serviq is a multi-tenant AI customer-operations platform. It is designed to
combine grounded retrieval, customer-specific typed tools, deterministic policy
and approval controls, a bounded agent, human handoff, and auditable operations.
The reference product uses synthetic DoorDash-like support scenarios and a
separate Stripe-like payment/refund integration; it is unaffiliated with either
company and must never move real money in the demo environment.

The repository contains a credible foundation, not an end-to-end product.
Tenant/RBAC, invitations, provider/model configuration, knowledge-source
registration/uploads, schema migrations, CI/security workflows, and supporting
infrastructure exist. Retrieval, conversations, the agent runtime, tools and
policies, human support workflows, product UIs, analytics/privacy operations,
and production deployment do not yet exist.

Do not infer runtime completion from a design document, migration, route stub,
or Linear status. The evidence ladder is: implemented code, focused test,
cross-service integration test, end-to-end flow, then deployed acceptance.

## Repository layout

| Path | Responsibility | Current state |
|---|---|---|
| `apps/tenant-console` | Tenant/workforce Next.js surface | Scaffold page only |
| `apps/customer-web` | End-customer Next.js surface | Scaffold page only |
| `apps/platform-console` | Separate platform-operator surface | Scaffold page only |
| `services/api` | FastAPI control plane and domain APIs | Active; most implemented surface |
| `services/worker` | Durable asynchronous execution | Minimal health/entrypoint foundation |
| `services/llm-gateway` | Provider abstraction/connectivity | Active adapters and internal test route |
| `packages/*` | Shared TypeScript packages | Early scaffolding |
| `infra/docker/compose.yml` (Keycloak service) | Local identity provider | Keycloak 26.7.1 service; V1.1.15 adds a deterministic test-only realm/client fixture at `infra/keycloak/serviq-test-realm.json`, mounted only by the opt-in integration harness |
| `infra/observability` | OTel, Prometheus, Grafana, Loki, Tempo | Templates; little app instrumentation |
| `migrations` | Alembic schema history | Ten revisions through durable knowledge-upload cleanup intents |
| `docs` | Product, architecture, operations, evidence | Extensive; contracts are not implementation |

The intended shape is a modular monolith for control-plane APIs, a durable
worker for asynchronous jobs, and an independently bounded LLM gateway. Avoid
splitting new services unless observed scaling, isolation, or ownership needs
justify it.

## Runtime and dependencies

- Node: `.nvmrc` pins `24.18.0`; workflows use pnpm `10.15.0`.
- Web: Next.js `16.3.1`, React `19.2.0`, TypeScript `5.9.3`, Tailwind `4.3.3`.
- Python: `>=3.14,<3.15` for API, worker, and LLM gateway.
- API: FastAPI, SQLAlchemy async, Alembic, Pydantic, PostgreSQL/pgvector.
- Gateway: OpenAI, Anthropic, and Google GenAI adapters behind a normalized
  provider contract.
- Local infrastructure: PostgreSQL/pgvector, Keycloak, Valkey, and SeaweedFS
  through its S3-compatible API. Redpanda and observability are optional
  Compose profiles.

The API, worker, and LLM gateway each have a committed `uv.lock`. The root
Makefile checks lock freshness and uses frozen installs/exports so local setup,
CI, release validation, and Python dependency auditing consume reviewed lock
state.

## Conventions

### Python services

- Source uses a `src/` layout; tests live under each service's `tests/`.
- FastAPI routers are thin; domain work belongs in service modules.
- SQLAlchemy access is asynchronous; Pydantic defines public boundaries.
- Ruff, mypy, and pytest are mandatory quality tools.
- IDs are opaque UUIDs. Organization scope is established server-side.

### TypeScript applications

- All three Next.js applications use the App Router.
- Share code only when at least two consumers need the same contract.
- ESLint and `tsc --noEmit` are active. There are no JavaScript test scripts,
  so a successful recursive `pnpm test` is not UI test evidence.

### API behavior

- Versioned external routes use `/api/v1`; gateway-only routes use `/internal`.
- Health endpoints are `/health/live` and `/health/ready`.
- Provider credentials are write-only at the public boundary.
- Logs should contain bounded IDs, counts, outcomes, and timings, not tokens,
  prompts, raw documents, credentials, or personal data.

## Authentication and authorization

Implemented foundations include OIDC/JWT validation and user provisioning,
organization membership and active-organization resolution, permission checks,
organization invitation flows, seeded workforce roles/permissions, and
provider/model/knowledge permissions.

The workforce validator resolves discovery/JWKS from the configured issuer,
requires the configured audience, verifies RS256 signatures and temporal
claims, requires a non-empty subject, and normalizes only the approved trusted
identity fields. V1.1.15 adds a deterministic, test-only Keycloak realm/client
fixture and an opt-in integration test that exercises this existing validator
against a token issued by the real local Keycloak service. The fixture is not a
production IdP configuration and is not loaded by the ordinary local Compose
stack unless the integration harness explicitly mounts it.

The live integration path proves a real issued token succeeds, wrong audience
and wrong issuer fail closed through real Keycloak metadata/JWKS, disabled and
unknown test users cannot obtain tokens, tenant/permission claims do not enter
the trusted identity DTO, and raw tokens do not appear in captured Python logs
or safe authentication errors. The direct password grant exists only on the
deterministic test client so CI can obtain a token non-interactively; the
product architecture remains Authorization Code + PKCE for workforce browser
login.

The external API authentication is workforce-oriented. Customer identity and
session boundaries and full platform-console isolation remain future work. A
browser-level proof for all three trust surfaces does not exist.

## Implemented HTTP surface

- organizations: create, list, read, update;
- invitations: create, list, revoke, accept;
- organization members: list and update role/state;
- provider connections: CRUD and connectivity test;
- model configurations: create, list, update, delete;
- knowledge sources: URL/sitemap registration and PDF/Markdown/text uploads;
- service liveness/readiness;
- internal normalized provider-connectivity testing.

Knowledge sources can be registered and stored, but the complete
fetch/parse/chunk/embed/index/retrieve lifecycle is pending.

## Data and migrations

Alembic revisions cover baseline identity/organizations, tenant/RBAC,
invitations, workforce permissions, providers/models, provider permissions,
model references, knowledge sources/documents/chunks, and knowledge permissions.
Mapped models include users, organizations, memberships, roles, permissions,
invitations, providers, model configurations/references, and knowledge sources.

Migration upgrade/downgrade/re-upgrade is exercised in CI against PostgreSQL.
Production migration runbooks, backup/restore evidence, and rollback drills are
not present.

## Testing and delivery

Primary commands are `make setup`, `make lint`, `make typecheck`, `make test`,
`make compose-config`, and `make security`. CI includes quality checks, real
PostgreSQL migration/integration checks, object-storage integration checks, and
V1.1.15 adds a dedicated live Keycloak workforce OIDC integration job. A
separate security workflow includes CodeQL, Gitleaks, Trivy, and dependency
audits. A release workflow is source-quality evidence, not deployed acceptance.

The Keycloak OIDC integration is opt-in outside its dedicated CI job through
`SERVIQ_KEYCLOAK_OIDC_INTEGRATION=1`. CI reuses the existing Compose Keycloak
service definition, mounts `infra/keycloak/serviq-test-realm.json` only into a
one-off container, starts Keycloak with `start-dev --import-realm`, waits for
both management readiness and realm discovery, runs only the live OIDC test
module, and always removes the test container. Readiness-timeout diagnostics are
bounded and token/secret-shaped values are redacted before output.

`make e2e` and `make load-test` intentionally fail because their harnesses do
not exist. There are no frontend tests. Many API integration tests are skipped
unless their infrastructure environment is enabled.

Audit results on 2026-08-22:

- all TypeScript apps: lint and type-check passed;
- TypeScript test command: exited successfully but ran no tests;
- API: Ruff/mypy passed; 78 tests passed, 61 integration tests skipped;
- worker: Ruff/mypy passed; 5 tests passed;
- LLM gateway: Ruff/mypy passed; 93 tests passed;
- Compose configuration rendered successfully;
- security scans, enabled PostgreSQL/object-store integration, browser E2E,
  load, deployment, and real-device acceptance were not run.

The V1.1.15 Keycloak integration evidence is newer than that 2026-08-22 audit
snapshot and should be interpreted from the ticket/CI run recorded when the
branch is finalized.

## Reusable implementation points

Reuse the existing OIDC helpers and the deterministic Keycloak integration
fixture for workforce trust-boundary regression tests. Keep the fixture
strictly test-only and do not turn its direct-access grant or placeholder users
into product login behavior. Also reuse permission/active-organization
dependencies, provider normalization and error mapping, knowledge object-storage
boundary, database/migration conventions, health patterns, and CI infrastructure
setup before adding parallel abstractions.

## Capability boundary

Implemented and evidenced at repository level:

- monorepo, tooling, local infrastructure, CI/security foundations;
- workforce identity, tenants, invitations, roles, permissions;
- provider/model configuration with secret-safe responses;
- knowledge registration/upload foundations;
- migrations and focused service tests.

Not implemented end to end:

- safe crawling, parsing, chunking, embeddings, indexing, hybrid retrieval;
- customer identity, conversations, messages, SSE;
- bounded agent execution, budgets, retries, and failure classification;
- demo tools, policy, confirmation, approval, reconciliation, compensation;
- human inbox, takeover, notes, tags, and resume;
- product-ready interfaces;
- analytics, audit export, privacy/retention operations;
- app telemetry, alerts, SLOs, incident runbooks;
- E2E/load harnesses and production deployment.

## Landmines and unknowns

- Linear's V1 percentage measures created foundation issues, not total scope.
- The staged roadmap has 198 additional tickets. Counts are not estimates, and
  several nominal 1–3 hour items are operational or multi-day programs.
- Embedding profile/index and hybrid-ranking decisions should precede retrieval
  schema and quality commitments.
- Customer identity, production secrets, deployment, E2E/load harnesses, and
  operational ownership remain unresolved.
- End-customer attachments remain a product decision.
- Design documents describe future behavior; verify an active code path.
- Keep demo integrations synthetic and idempotent; never use real payments or
  production customer data.

## Live tracker snapshot

At audit time, GitHub `anmolsansi/Serviq` had no open pull requests or issues,
and `main` held the latest merged release-reconciliation commit. Linear had 55
issues: 51 Done, one In Progress, and three In Review. OPE-300, OPE-302,
OPE-303, and OPE-304 remained non-terminal despite their relevant changes being
merged. That is tracking debt. The 198-ticket V1.3.05-to-V4 staged backlog was
not yet in Linear.

See `PROJECT_STATUS_AND_ROADMAP.md` for the reconciled product assessment and
execution recommendation.

## V1.3.04A current state — durable knowledge uploads

File-backed knowledge-source registration now has an implemented cross-store consistency boundary. Before the API attempts the generated raw-object PUT, it commits an internal tenant-owned `knowledge_upload_cleanups` row containing the source/object identity, generated key, retry state, bounded error code, and timestamps required for reconciliation.

On confirmed PUT success, the normal `knowledge_sources` insert and cleanup transition to `referenced` occur in the same PostgreSQL transaction. If source persistence fails, the pre-upload intent survives rollback. Request-time cleanup performs a best-effort immediate delete outside the database transaction while durable reconciliation remains available if deletion or the follow-up state write fails.

Generic storage PUT failures are treated as outcome-ambiguous rather than assumed absent. `prepared` work has a 15-minute stale deadline; due reconciliation uses the typed presence check before deletion. Confirmed cleanup replay starts at 30 seconds, then retries after 5 minutes and 30 minutes, with the third failed replay becoming `exhausted`.

Replay is internal, tenant-scoped, idempotent, and key-validated. Foreign-tenant access is rejected before storage I/O. Object keys, file data, credentials, and tokens are excluded from cleanup logs and status-count visibility. There is no public cleanup endpoint.

Alembic revision `20260824_0010` adds the schema and refuses downgrade while unresolved cleanup obligations exist. The worker remains a scaffold: this ticket implements the durable reconciliation service contract but does not claim a general transactional outbox, broker consumer, scheduler, cleanup UI, or resolved-row purge job is deployed.

Primary evidence is ADR-018, CCR-006, `KNOWLEDGE_UPLOAD_CONSISTENCY_RUNBOOK.md`, `V1.3.04A_SECURITY_RELIABILITY_REVIEW.md`, migration 0010, the knowledge cleanup/service/repository modules, and PostgreSQL/S3-compatible integration tests.

The exact implementation head `22ad508fc148f68759b4b0466323e9ce6e452c1c` passed CI and Security before PR #180 merged it into `main` as `ae9c2d67b8e09b3db62e824b7868fa3e163324b0` on 2026-08-26.

