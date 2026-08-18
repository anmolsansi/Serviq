# Serviq Technology Stack

**Status:** Technology baseline v1.1  
**Scope:** Production V1 and its local-to-cloud scale path  
**Authority:** This document freezes technology choices. `ARCHITECTURE.md` owns contracts, folder boundaries, schemas, APIs, and deployment behavior. Builders do not add or replace dependencies without an architect-approved ticket or ADR.

## 1. Technology Principles

1. Core local development must run without mandatory paid infrastructure.
2. Production code must remain cloud-portable even though AWS is the intended first cloud target.
3. The stack must support a polished TypeScript frontend and Python-heavy AI/backend workloads.
4. Start with a modular monolith and durable workers. Extract services only when scale, fault isolation, or team ownership justifies it.
5. Provider-specific AI SDKs stay behind the Serviq LLM gateway adapter.
6. Every external dependency must have a timeout, failure mode, test double, and observability plan.
7. Dependencies are pinned by lockfiles. No production build uses floating `latest` tags.
8. Security patches can advance patch versions without a product decision. Major/minor upgrades require an explicit dependency/architecture review.

## 2. Baseline Versions

Initial scaffold baseline, verified for the August 2026 planning snapshot:

| Concern | Baseline |
|---|---|
| Next.js | 16.2.x Active LTS. Scaffold should use the current patched 16.2 release. |
| React | 19.2.x |
| TypeScript | Current stable 5.x supported by the selected Next.js release, exact version locked in `pnpm-lock.yaml`. |
| Python | 3.14.x. Scaffold baseline 3.14.6 or later security patch in the 3.14 line. |
| FastAPI | 0.140.x. Scaffold baseline 0.140.13 or later compatible security/fix patch. |
| Pydantic | 2.x, exact version locked by `uv.lock`. |
| SQLAlchemy | 2.x, exact version locked by `uv.lock`. |
| Alembic | Current SQLAlchemy-2-compatible stable release, exact version locked by `uv.lock`. |
| PostgreSQL | 18.x. Scaffold baseline 18.4 or later security patch in the 18 line. |
| Keycloak | 26.7.x or later compatible security patch in the selected supported line. |
| Node.js | Current LTS supported by Next.js 16.2, exact version frozen in `.nvmrc`/toolchain file at scaffold time. |

`docs/repo_context.md` becomes the source of truth for the exact versions actually installed after the repository is scaffolded.

## 3. Repository and Package Model

Serviq uses a monorepo.

```text
Serviq/
  apps/
    client-console/
    customer-web/
    platform-console/
  services/
    api/
    worker/
    llm-gateway/
  packages/
    ui/
    contracts/
    config/
    observability/
    security/
    testkit/
  infra/
    docker/
    kubernetes/
    terraform/
  docs/
    adr/
    architecture/
    runbooks/
  scripts/
```

Package managers:

- JavaScript/TypeScript: `pnpm` workspaces with one root lockfile.
- Python: `uv` with committed lockfile(s) and reproducible environments.
- Root task entry: Makefile or Taskfile. The first scaffold ticket freezes one and all subsequent tickets reuse it.

## 4. Frontend Stack

### 4.1 Core

- Next.js 16.2.x App Router.
- React 19.2.x.
- TypeScript strict mode.
- Server components by default where appropriate.
- Client components only when browser interactivity requires them.

### 4.2 Data and Forms

- TanStack Query for interactive server-state caching and mutations.
- `react-hook-form` for forms.
- Zod for browser validation and feature schemas.
- Server validation remains authoritative. Frontend schemas must mirror the API ticket exactly.
- No global state library in Production V1 unless a future ticket identifies state that cannot be cleanly owned by a feature or server-data layer.

### 4.3 Styling and Design System

- Tailwind CSS.
- Accessible headless primitives selected during scaffold and frozen in the first frontend ADR.
- Serviq-owned shared components in `packages/ui`.
- Design tokens for typography, spacing, radius, elevation, status semantics, and responsive breakpoints.
- Storybook for shared component documentation and state review.

Shared component candidates:

```text
Button
IconButton
Input
Select
Checkbox
RadioGroup
Textarea
FormField
Dialog
Drawer
Popover
Tooltip
Toast
Tabs
Table
Pagination
Skeleton
EmptyState
ErrorState
PermissionDenied
StatusBadge
MetricCard
Timeline
SourceCitation
ConversationMessage
ActionConfirmationCard
ApprovalStatusCard
```

### 4.4 Streaming

- Server-Sent Events are the default for server-to-customer support updates.
- WebSockets are not part of V1 unless a later contract proves bidirectional persistent transport is required.
- SSE event types are frozen in `ARCHITECTURE.md`.

### 4.5 Frontend Quality Tooling

- ESLint.
- TypeScript strict checks.
- Prettier or the formatter frozen by scaffold. Do not use competing formatters.
- Vitest.
- Testing Library.
- Playwright.
- automated accessibility checks in critical component/E2E paths.
- visual regression for shared design-system components and the core support/inbox workflows before portfolio-ready release.

## 5. Backend Stack

### 5.1 Runtime and Framework

- Python 3.14.x.
- FastAPI 0.140.x.
- Pydantic 2.x.
- Uvicorn-compatible ASGI runtime for local/dev. Production process topology is defined by deployment tickets and benchmark results.

### 5.2 Persistence

- SQLAlchemy 2.x.
- Alembic migrations.
- PostgreSQL 18.x.
- PostgreSQL RLS as defense in depth where the connection/request model permits it safely.
- pgvector extension for V1 vector storage.
- PostgreSQL full-text search for V1 lexical retrieval.

### 5.3 Backend Module Rule

Every module follows the layering frozen in `ARCHITECTURE.md`:

```text
router.py -> service.py -> repository.py -> database
schemas.py
models.py
permissions.py
```

Business logic does not live in routers or ORM models. Modules do not import another module's repository.

### 5.4 Backend Tooling

- Ruff for lint/format policy.
- mypy with a strictness profile frozen during scaffold.
- pytest.
- pytest-asyncio or the async test approach frozen by scaffold.
- Testcontainers or Docker-backed real integration dependencies.
- Hypothesis for selected policy, idempotency, parsing, and state-machine property tests.
- pre-commit hooks only for fast deterministic checks. CI remains authoritative.

## 6. Data, Cache, Search, and Storage

### 6.1 PostgreSQL

Primary source of truth for tenant, identity mapping, configuration, conversations, workflow state, approvals, support state, audit metadata, idempotency, and outbox data.

Database conventions are frozen in `ARCHITECTURE.md` and `database_rules.md`. No ticket invents a table, field, constraint, or index outside those contracts.

### 6.2 pgvector + Full-Text Search

V1 retrieval uses PostgreSQL for both lexical and vector storage so the project can be developed locally at zero infrastructure cost beyond the database container.

A V1 embedding dimension/model must be frozen in an ADR before creating a production vector index. Until then, the architecture allows non-indexed/dev embedding storage but builders may not guess an index dimension.

A dedicated vector engine or OpenSearch cluster is **not** a V1 dependency. It is introduced only after benchmark evidence shows the retrieval service needs it.

### 6.3 Valkey-Compatible Cache

Used only for rebuildable/ephemeral state:

- rate-limit counters;
- short-lived session/cache data where the architecture assigns it;
- hot tenant/agent configuration;
- exact/semantic response cache metadata;
- provider health/circuit state;
- request coalescing/deduplication;
- short-lived coordination.

Key format:

```text
serviq:{env}:{tenantId}:{domain}:{id}
```

Every cache key has a TTL unless a ticket explicitly documents why it does not. Cache loss must not lose a completed business mutation.

### 6.4 Object Storage

- Local: the S3-compatible implementation frozen in Compose, currently SeaweedFS.
- AWS: Amazon S3.
- Access always goes through the Serviq object-storage adapter.
- Python API S3 client: AWS-maintained `botocore` 1.42.x, exact patch locked by `services/api/uv.lock`, as frozen by ADR-016.
- The adapter uses explicit connect/read timeouts and one total SDK attempt. Feature modules do not own SDK retry behavior.
- Bucket layout, MIME allowlists, file limits, and generated object keys are defined in `ARCHITECTURE.md`.
- Application code uses typed UUID-based key helpers. It does not accept user filenames or arbitrary full object keys as storage paths.

## 7. Events and Background Work

### 7.1 Broker

Serviq uses Kafka-compatible event semantics for durable domain events and worker queues that require partitioning/consumer groups.

- Local optional profile: Redpanda.
- AWS scale path: Amazon MSK or another ADR-approved managed Kafka-compatible service.

The event broker is not the transaction source of truth. Transactional services write `outbox_events` in PostgreSQL and an outbox publisher delivers events.

### 7.2 Worker Rules

- Durable work never depends only on FastAPI `BackgroundTasks` or process memory.
- Jobs are idempotent.
- Retries are bounded.
- Dead-letter behavior is explicit.
- Each job records/derives observable status.
- External calls do not run inside database transactions.

Exact topics, retry schedules, and idempotency keys are in `ARCHITECTURE.md`.

## 8. Authentication, Authorization, and Secrets

### 8.1 Workforce Identity

- Local/dev OIDC provider: Keycloak 26.7.x.
- Flow: Authorization Code + PKCE.
- Access/refresh tokens stay server-side.
- Browser session uses an opaque/encrypted `HttpOnly` cookie, `Secure` in production, `SameSite=Lax` unless a reviewed channel contract requires otherwise.

No passwords, JWT signing, or session cryptography is hand-rolled by feature code.

### 8.2 Customer Identity

Separate trust domain from workforce identity:

- anonymous session for public support;
- tenant-signed short-lived assertion for verified customer context in V1;
- future OIDC/OAuth connectors behind the customer identity adapter.

### 8.3 Authorization

- Serviq capability model.
- Tenant-scoped roles and object ownership.
- Server-side guard + service/repository ownership checks.
- PostgreSQL RLS defense in depth where configured.
- Deny by default.
- Platform-operator authorization is separate from tenant roles.

### 8.4 Secrets

Local:

- ignored local secret files/environment values for platform bootstrap secrets;
- tenant BYOK values stored through the secret adapter, never in tracked fixtures.

Production AWS mapping:

- AWS Secrets Manager and/or Parameter Store after an ADR freezes the exact split.

Rules:

- no secret in client bundles;
- no secret in logs/traces/test fixtures;
- provider secret shown only at creation if the UI needs confirmation, then masked;
- secret rotation and provider-key lifecycle metadata are auditable without storing the secret value in audit events.

## 9. LLM and Agent Stack

### 9.1 Provider-Neutral Gateway

Serviq owns the internal request/response contract. A self-hosted LiteLLM-compatible adapter may implement provider translation, but domain code imports Serviq contracts, not LiteLLM/provider SDK response types.

Initial provider adapters:

- OpenAI;
- Anthropic;
- Gemini;
- OpenRouter.

Capabilities:

- streaming generation;
- structured output;
- model aliases;
- timeout budgets;
- ordered fallbacks;
- usage normalization;
- error normalization;
- provider-health/circuit state;
- BYOK credential resolution.

### 9.2 Agent Runtime

Serviq implements an explicit state machine owned by the domain. No unconstrained `while model_wants_tool` loop is permitted.

Run controls:

- step budget;
- model-call budget;
- tool-call budget;
- wall-clock budget;
- token/output budget;
- retry budget;
- policy gates;
- deterministic completion/failure/escalation.

### 9.3 Prompt and Model Safety

- System instructions and untrusted user/retrieved/tool data are separated.
- Retrieved web content is data, never instruction authority.
- Model-produced structured tool arguments are schema-validated.
- The model cannot choose arbitrary server URLs, SQL, shell commands, or code execution.
- Full prompts containing PII are not logged by default.

### 9.4 AI Evaluation

Versioned evaluation datasets cover:

- grounded answer correctness;
- citation correctness;
- unsupported-answer behavior;
- prompt-injection resistance;
- tool selection;
- tool argument correctness;
- policy compliance;
- approval/escalation behavior;
- provider/model regression.

CI uses deterministic fake model responses for contract tests. Optional evaluation jobs may use a contributor's own provider key outside required free CI.

## 10. Observability Stack

### 10.1 Standard

OpenTelemetry is the instrumentation standard across Python services and supported frontend/server boundaries.

### 10.2 Local Profile

- OpenTelemetry Collector.
- Prometheus.
- Grafana.
- Loki.
- Tempo.

This is an optional Compose profile for developer resource control. Application instrumentation is not optional.

### 10.3 Production Rules

- structured JSON logs;
- stable error codes;
- request/trace/correlation IDs;
- tenant context only where safe;
- PII/secret redaction;
- bounded metric cardinality;
- health/readiness endpoints defined in architecture.

A hosted observability vendor is not a V1 dependency.

## 11. Testing Stack

### 11.1 Backend

- pytest unit tests for business logic.
- real PostgreSQL/Valkey/broker integration tests through Docker/Testcontainers where the ticket requires them.
- API tests for every route, including exact response shape, validation, 401, 403, 404, and conflict paths.
- migration up/down tests.
- tenant-isolation tests.
- property tests for selected policy/idempotency state.

### 11.2 Frontend

- Vitest.
- Testing Library using accessible role/label queries.
- Playwright end-to-end.
- required loading, empty, error, permission, and success state coverage.
- form validation/pending/double-submit tests.

### 11.3 Contract Tests

Frozen contracts cover:

- OpenAPI request/response/error shapes;
- LLM gateway normalized responses/errors;
- tool schemas;
- event envelopes;
- SSE public events;
- webhook signatures;
- tenant/customer auth context.

A contract change cannot be merged by silently changing tests. It requires architect change control.

### 11.4 Performance and Scale

k6 scenarios are stored in the repository and report separately:

- non-LLM REST throughput;
- concurrent SSE clients;
- message write/read paths;
- cached deterministic paths;
- retrieval throughput;
- worker/event throughput;
- tool-service mocks;
- fake-provider agent throughput.

External paid LLM quotas are never used to claim Serviq internal throughput.

## 12. Security Tooling

Public repository CI uses free/open tooling where practical:

- GitHub CodeQL;
- Gitleaks;
- Trivy;
- dependency vulnerability scanning;
- Semgrep or equivalent targeted rules;
- SBOM generation for release artifacts;
- dependency update automation;
- license inventory.

Required application controls:

- SSRF protection for knowledge crawling;
- strict source URL/domain validation;
- input validation and output encoding;
- CORS allowlist;
- CSRF defense for cookie-authenticated mutations;
- request/file size limits;
- rate limiting;
- tenant isolation;
- secure cookies;
- prompt-injection boundaries;
- tool allowlists;
- idempotency;
- audit for sensitive operations.

Auth, permissions, encryption, webhooks, public upload surfaces, LLM prompts containing user data, and destructive migrations require premium review.

## 13. Local Development Profiles

`docker compose` is the local platform orchestrator. The exact compose filenames are frozen by the scaffold ticket.

### Core profile

```text
client-console
customer-web
platform-console
api
worker
postgres + pgvector
valkey
object-storage
keycloak
llm-gateway or fake-llm-gateway
```

### Events profile

```text
redpanda
worker consumers that require event topics
```

### Observability profile

```text
otel-collector
prometheus
grafana
loki
tempo
```

The application must be usable in deterministic demo/test mode without a paid AI key. Real AI behavior requires the contributor's BYOK provider credential.

## 14. AWS Scale Mapping

| Concern | Local/V1 | AWS scale path |
|---|---|---|
| Edge/CDN | local reverse proxy | CloudFront |
| WAF | local request controls | AWS WAF |
| Load balancing | local proxy | ALB/NLB as workload requires |
| Containers | Docker Compose | ECS or EKS selected by deployment ADR after measured need |
| PostgreSQL | local PostgreSQL 18 | RDS/Aurora PostgreSQL-compatible path after compatibility review |
| Vector | pgvector | pgvector first. Dedicated vector only after retrieval benchmark/ADR. |
| Cache | Valkey-compatible local | ElastiCache-compatible managed cache |
| Broker | Redpanda local profile | MSK or ADR-approved Kafka-compatible managed service |
| Object storage | MinIO/S3-compatible | S3 |
| Secrets | local secret adapter | Secrets Manager/Parameter Store split by ADR |
| Observability | OTel + OSS profile | OTel with managed or self-hosted backend chosen by ADR |
| DNS | local hosts | Route 53 |
| IaC | none required for local | Terraform |

ECS vs EKS is not a builder decision and is not required for Production V1 local completion. It is a later deployment ADR driven by scale and operations requirements.

## 15. CI/CD

GitHub Actions pull-request gates:

1. formatting;
2. lint;
3. TypeScript/Python type checks;
4. unit tests;
5. API/integration tests;
6. tenant-isolation and permission tests;
7. contract tests;
8. migration up/down tests;
9. secret scan;
10. dependency/SAST scans;
11. container build validation for touched services;
12. affected E2E smoke tests;
13. docs/link validation.

Release pipeline later adds:

- immutable image digests;
- SBOM;
- artifact signing;
- staging deployment;
- migration preflight;
- smoke/E2E/security gates;
- controlled promotion;
- rollback/runbook linkage.

No production deployment workflow is merged before the target environment and rollback behavior are frozen in a deployment ADR.

## 16. Dependency Change Policy

A builder may not add, remove, or replace a dependency unless its ticket names the exact dependency and purpose.

Architect approval/ADR is required when a change introduces or replaces:

- auth/session libraries;
- ORM/migration tools;
- message brokers;
- vector/search engines;
- workflow engines;
- LLM orchestration frameworks;
- UI component systems;
- state-management libraries;
- cloud-specific SDKs used outside adapters;
- security/crypto libraries.

Security-only patch upgrades within a frozen compatible line may be handled by dependency automation and reviewed normally.

## 17. Technologies Explicitly Not in Production V1

The following are not available for builders to introduce without a new ADR and measured need:

- a service mesh;
- a dedicated vector database;
- a dedicated OpenSearch cluster;
- a separate workflow engine such as Temporal;
- Kubernetes as a mandatory local dependency;
- a second backend language for core services;
- GraphQL for V1 APIs;
- arbitrary agent code execution/sandbox;
- a global frontend state store;
- client-side direct calls to OpenAI, Anthropic, Gemini, or OpenRouter;
- a paid SaaS dependency required for deterministic local development or CI.

## 18. Final Baseline

```text
Frontend:          Next.js 16.2.x + React 19.2 + TypeScript
Forms:             react-hook-form + Zod
Server state:      TanStack Query where required
Styling:           Tailwind + Serviq UI package
Backend:           Python 3.14.x + FastAPI 0.140.x + Pydantic 2.x
ORM/Migrations:    SQLAlchemy 2.x + Alembic
Primary DB:        PostgreSQL 18.x
Retrieval V1:      PostgreSQL FTS + pgvector
Cache:             Valkey-compatible
Events:            Kafka-compatible contract; Redpanda local profile
Storage:           S3-compatible adapter; MinIO local, S3 cloud
Auth local:        Keycloak OIDC
LLM:               Serviq gateway + OpenAI/Anthropic/Gemini/OpenRouter adapters
Observability:     OpenTelemetry + Prometheus/Grafana/Loki/Tempo local profile
Tests:             pytest + Vitest + Testing Library + Playwright + k6
Local runtime:     Docker Compose profiles
CI/CD:             GitHub Actions
Cloud IaC:         Terraform when AWS deployment begins
```
