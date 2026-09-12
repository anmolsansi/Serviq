# Serviq Repository Context

> Audited 2026-09-12 at `main` / `origin/main`
> `3e1b9aa0a9b6d38238d844a1eeb96aaa89365a02`.
> [System audit and evidence](SYSTEM_AUDIT_2026-09-12.md) ·
> [Build Guide](SERVIQ_BUILD_GUIDE.md) ·
> [Canonical backlog](SERVIQ_REMAINING_LINEAR_TICKETS_FULL.md).

## Executive snapshot

Serviq is a multi-tenant AI customer-operations platform under construction.
Workforce/tenant/provider/knowledge foundations exist; the customer support,
agent, tool/policy/approval and human-support product journeys do not. The demo
uses synthetic delivery and payment/refund data and must not move real money.

The API registers functional domain routers but lacks the authentication/session
composition that populates their trusted principal dependencies. The worker
publishes outbox events and consumes knowledge sync work through durable parse
handoff. Normalization and chunking are pure libraries awaiting activation.
Embeddings have a private fake-only gateway route. All three web apps are static
scaffolds. A successful library test or metadata record is not end-to-end acceptance.

## Stack and folder map

Manifest/config evidence: root and app `package.json`, `.nvmrc`, service
`pyproject.toml`/`uv.lock`, `pnpm-lock.yaml`, `.github/workflows/ci.yml`.

- Node `24.18.0`; CI pnpm `10.15.0`, Python `3.14.6`, uv `0.12.9`.
- Next.js `16.3.3`, React `19.2.0`; TypeScript, Tailwind and ESLint per locked workspace.
- Python services require `>=3.14,<3.15`; FastAPI, Pydantic, SQLAlchemy async,
  Psycopg 3 and Alembic in the API; confluent-kafka, pypdf and storage in the worker.
- Gateway SDK pins: OpenAI `2.53.0`, Anthropic `0.121.0`, Google GenAI `2.17.0`.
- Local infrastructure: PostgreSQL/pgvector, Keycloak, Valkey, SeaweedFS; optional
  Redpanda and observability profiles.

| Path | Responsibility / actual state |
|---|---|
| `apps/client-console/src/app` | Workforce operations scaffold; not `apps/tenant-console` |
| `apps/customer-web/src/app` | End-customer scaffold |
| `apps/platform-console/src/app` | Platform operator scaffold |
| `services/api/app/core` | Auth/principal/config/database/storage/secrets/error primitives |
| `services/api/app/modules` | Organizations, workforce, tenancy, invitations, members, providers, knowledge, health |
| `services/api/alembic/versions` | 12 migrations through `20260902_0012` outbox |
| `services/worker/app/consumers` | Knowledge sync and retry-topic consumer |
| `services/worker/app/jobs` | Outbox publisher and knowledge fetch/document/parse-handoff job |
| `services/worker/app/core` | Fetch/normalization/chunking/storage/broker/config primitives |
| `services/llm-gateway/app` | C-4 models, provider generation adapters, connectivity and fake embedding routes |
| `packages/contracts/src` | Shared API/auth/event contract foundations |
| `packages/ui/src` | Placeholder design tokens/export surface |
| `packages/observability`, `packages/security`, `packages/testkit` | Empty export scaffolds awaiting dedicated tickets |
| `infra/docker` | Compose and optional observability configuration |
| `infra/keycloak/serviq-test-realm.json` | Test-only realm; not ordinary production login config |
| `tests/frontend` | Four smoke/config tests |
| `docs` | Specs, ADRs/CCRs, runbooks, audit and backlog |

Python source lives in `app/`, not `src/`. Source discovery must use the current
checkout when an older graph disagrees with these entrypoints. Do not extend an
invented legacy folder or treat shared placeholder packages as implemented logic.

## Conventions and reusable boundaries

Python uses snake_case modules/functions, thin FastAPI routers, Pydantic request/
response models and async service/repository functions. Tests are `test_*.py` in
service `tests/`; integration tests live in `tests/integration/`. Examples inspected
include organization, provider and knowledge routers/services/models and their
integration tests. Frontend components use App Router `page.tsx`/`layout.tsx`;
all three page components currently render a heading and explanatory scaffold text.

Reuse these boundaries:

- `services/api/app/core/api.py`: strict `SuccessEnvelope` and `ErrorEnvelope`.
- `services/api/app/core/http_errors.py`: stable authentication/core/validation errors.
- `services/api/app/core/database.py`: one async engine/session pattern with explicit
  transaction ownership; repositories receive `AsyncSession`.
- `services/api/app/core/auth.py`: OIDC metadata/JWKS cache and RS256 validation.
- `services/api/app/core/principal.py`: trusted request-state readers; **not middleware**.
- `services/api/app/modules/workforce/service.py`: verified identity → internal user,
  including disabled-user rejection and concurrent insert recovery.
- `services/api/app/modules/tenancy/service.py`: active membership and effective permissions.
- `services/api/app/core/rate_limits.py`: shared Valkey limiters, not provider-owned copies.
- `services/api/app/core/object_storage.py`: typed tenant/source keys and object operations.
- `services/api/app/modules/knowledge/cleanup.py`: bounded durable cleanup replay.
- `services/worker/app/core/public_knowledge_fetch.py`: bounded SSRF-safe fetch.
- `services/worker/app/core/knowledge_normalization.py`: pure immutable segments.
- `services/worker/app/core/knowledge_chunking.py`: pure deterministic chunk/provenance policy.
- `services/llm-gateway/app/schemas/c4.py`: normalized provider and embedding contracts.
- `services/llm-gateway/app/http_boundary.py`: private-route pre-parse authentication,
  transport-body limits, and input-safe validation responses.

## Authentication and API style

The intended workforce browser flow is Authorization Code + PKCE with provider
tokens kept server-side (`ARCHITECTURE.md`, workforce login/session section).
Existing `WorkforceOidcValidator` checks issuer/audience/signature/expiry and exposes
only approved identity fields. Membership and permission services use server-owned
identity rather than trusting tenant/permission JWT claims.

**Composition gap:** no production caller writes `serviq_user_id`,
`serviq_workforce_identity` or `serviq_tenant_id` on request state. `app/main.py`
only installs error handlers and routers. Route tests override principal dependencies;
Keycloak integration tests call the validator directly. V1.1.16 owns the missing
session/principal handoff. Do not add a user-controlled identity header to make
protected routes work. Customer and platform trust surfaces remain unimplemented.

Public route families at `/api/v1`: organizations; organization invitations and
members; invitation acceptance; provider connections and connectivity tests;
model configurations; knowledge-source list/create (JSON or multipart) and sync.
API health is `GET /health/live` and `GET /health/ready`; readiness checks PostgreSQL,
not the complete broker/storage/gateway/ingestion journey.

The API success shape is `{"data": ...}` and safe errors use
`{"error":{"code":"...","message":"..."}}`, with optional field errors.
List routes currently return arrays inside `data`; do not invent a universal
pagination cursor. Example from the isolated principal diagnostic:

```http
GET /api/v1/organizations
Authorization: Bearer <synthetic test value>

HTTP/1.1 401 Unauthorized
{"error":{"code":"UNAUTHENTICATED","message":"Authentication required."}}
```

That probe replaced only the DB dependency to isolate missing authentication
composition; the unmodified local arm64 app instead hit the greenlet-related 500.
It is not a successful authenticated API example.

Gateway routes are `POST /internal/v1/provider-connectivity-test` and
`POST /internal/v1/embeddings`. Private body requests now cross a shared ASGI
boundary that validates `LLM_GATEWAY_INTERNAL_TOKEN` before FastAPI parses the
body, enforces a finite transport-body cap using both declared and received bytes,
and replaces Pydantic/FastAPI validation details with a fixed input-safe 422 shape.
Route-level token checks remain defense in depth. Gateway responses keep their
service-specific shapes rather than the API envelope. Provider generation/streaming
adapters exist, but no agent/generation HTTP journey is composed by
`services/llm-gateway/app/main.py`.

## Data, jobs and lifecycle

Alembic revisions 0001–0012 cover baseline identity, RBAC, invitations, workforce
roles, provider/model metadata and permissions/references, knowledge sources/
documents/chunks and permissions, upload cleanup, upload reservations, and outbox.
The head is `20260902_0012`. Use `cd services/api && uv run alembic upgrade head`
only against the intended database with configured settings. CI exercises a
fresh PostgreSQL database and downgrade/re-upgrade; no production restore drill
is proven. Cleanup/quota/outbox downgrades have pending-state guards.

Tables use snake_case, UUID IDs and timestamps. Tenant filtering is explicit in
repositories/jobs; do not assume DB RLS or composite tenant foreign keys enforce
every relationship. `knowledge_chunks` already has text/metadata, nullable
**dimensionless** vector and a generated text-search column/GIN index. There is
no vector ANN index or active retrieval repository. V1.3.12 owns that migration.

Knowledge registration/upload and sync are separate operations. A sync command
locks the source, increments `sync_version`, sets `syncing` and inserts the sync
outbox record atomically. The publisher sends at least once; the sync consumer
uses manual offsets, bounded retry delays and DLQ. It fetches URL/file bytes and
commits a versioned document plus parse event. It keeps the source `syncing` until
later indexing succeeds. Sitemap sync is deliberately unsupported (ADR-023).

Upload durability/quota primitives exist, but the cleanup sweep is unscheduled;
pre-parser resource admission and URL raw-version accounting are missing.
V1.3.09A explicitly owns parse-event consumption/persistence/index handoff.
ADR-024/025 normalizers and ADR-026 chunker must be reused, not reimplemented.

ADR-027 fixes alias `serviq-embedding-v1`, 1536 dimensions, at most 100 inputs,
32,000 characters per input. Only `FakeLLMAdapter` implements the route. Its
`provider=openai` field with `upstreamModel=serviq-fake-v1` does not represent a
real OpenAI call. Real semantic transport and safe profile/reindex policy remain
V1.3.11B. V1.3.11A now closes the input-validation privacy gap at the shared HTTP
boundary while preserving the fake adapter for deterministic tests. PR #222 is
merged as `26784e7` for the original embedding profile.

## Setup, testing and delivery

Use `make setup`, `make lint`, `make typecheck`, `make test`, `make security`.
Compose validation is `docker compose -f infra/docker/compose.yml --profile '*'
config --no-interpolate`; there is no `make compose-config` target. `make dev`
starts infrastructure, not the app processes. Export required service settings;
use distinct API/gateway/web ports and configure a host-reachable Kafka listener
for a host worker. Default Compose Redpanda is internal-only. See Build Guide.

Run one Python test from its service: `uv run pytest tests/test_database.py`.
Real integration tests require the named `SERVIQ_*_INTEGRATION=1` switches and
actual services. Test fixtures use synthetic values; do not enable integrations
against a shared database. API tenancy helpers live in `tests/support/tenant_isolation.py`.

The current audit ran 315 passing tests and 84 locally skipped infrastructure tests,
web lint/typecheck and all Ruff/mypy checks. Four root Vitest smoke/config tests
are real frontend tests; Playwright only lists zero tests. `make e2e` and
`make load-test` intentionally fail. Alternate webpack production builds passed
for all three apps; default Turbopack builds were environment-blocked.

Current-main CI and Security passed, including PostgreSQL migrations, object
storage and six live Keycloak validator tests. Worker/quota integration evidence
is from earlier path-filtered PR runs, not rerun on this main SHA. Dependency
audits found no known vulnerabilities in this run. See the audit for exact links
and limits; green CI is not deployed acceptance.

## Landmines, unknowns and next work

- Explicit `sqlalchemy[asyncio]` dependency ensures greenlet is available across all environments including macOS arm64 (V1.0.28 resolved).
- Workforce auth primitives are not wired into requests (V1.1.16).
- Multipart parsing precedes file-byte/concurrency enforcement (V1.3.04C).
- Upload cleanup lacks a runtime scheduler; URL fetch bytes lack equivalent
  accounting/recovery (V1.3.04D / V1.3.07A).
- Private gateway validation is redacted and authenticated before body parsing
  (V1.3.11A resolved); real semantic embedding transport remains V1.3.11B.
- Main has no branch protection/rulesets; reuse GitHub #205 (V1.0.29).
- Local encrypted secret storage uses file replacement plus an in-process lock.
  Production multi-process secret storage and rotation require a decision.
- Source-specific runbooks exist; comprehensive telemetry, privacy/retention,
  backup/restore, deployment and operating ownership are still missing.
- V2–V4 are staged plans, not implemented capabilities or approved estimates.

The live Linear project query returned 17 issues: 12 Done, 3 In Progress, 2 In
Review. OPE-306/307 have implemented code and closed GitHub issues but remain
In Progress; OPE-303/304/305 also remain nonterminal. The canonical file retains
14 implemented records and 201 backlog records, including 10 audit follow-ups.
No completion percentage should be inferred from these counts.
