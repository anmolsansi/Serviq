# Serviq Repository Context

> Audit ticket: OPE-270  
> Audited `main` commit: `5ccfe27a878af5aa32fe049fe7632d8e04bc221d`  
> Audit date: 2026-08-14  
> Purpose: give every later builder a factual map of what exists in Serviq now. This document records implemented repository reality, not future architecture wishes.

## 1. Repository snapshot

Serviq is a monorepo containing three Next.js applications, six shared TypeScript packages, three Python services, local Docker infrastructure, product/architecture documentation, and GitHub Actions workflows.

The repository is intentionally still foundation-heavy. Many important production capabilities have a defined future home but are not implemented yet. A folder name or placeholder module is not evidence that the corresponding subsystem exists.

The root workspace is controlled by:

- `package.json`
- `pnpm-workspace.yaml`
- `pnpm-lock.yaml`
- `.nvmrc`
- `.editorconfig`
- `.gitignore`
- `Makefile`

The root JavaScript workspace includes only `apps/*` and `packages/*`. Python services under `services/*` are intentionally managed with `uv`, not pnpm.

## 2. Exact toolchain and framework versions

### JavaScript / TypeScript

Evidence comes from `.nvmrc`, package manifests, and `pnpm-lock.yaml`.

- Node.js: `24.18.0` — `.nvmrc`
- pnpm used by CI: `10.15.0` — `.github/workflows/ci.yml`
- Next.js: `16.2.9` — app manifests / `pnpm-lock.yaml`
- React: `19.2.0` — app manifests / `pnpm-lock.yaml`
- React DOM: `19.2.0` — app manifests / `pnpm-lock.yaml`
- TypeScript resolved version: `5.9.3` — `pnpm-lock.yaml`; manifests currently declare `^5.1.0`
- Tailwind CSS resolved version: `4.3.3` — `pnpm-lock.yaml`
- `@tailwindcss/postcss`: `4.3.3` — `pnpm-lock.yaml`
- ESLint resolved version: `9.39.5` — `pnpm-lock.yaml`
- `eslint-config-next`: `16.2.9`
- `@types/node`: `24.13.3`
- `@types/react`: `19.2.18`
- `@types/react-dom`: `19.2.4`

The application manifests are:

- `apps/client-console/package.json`
- `apps/customer-web/package.json`
- `apps/platform-console/package.json`

The shared-package manifests are under:

- `packages/ui/package.json`
- `packages/contracts/package.json`
- `packages/config/package.json`
- `packages/observability/package.json`
- `packages/security/package.json`
- `packages/testkit/package.json`

### Python

All current Python services declare Python `>=3.14,<3.15` in their `pyproject.toml` files.

Services:

- `services/api`
- `services/worker`
- `services/llm-gateway`

The API and worker have committed uv lockfiles:

- `services/api/uv.lock`
- `services/worker/uv.lock`

The LLM gateway currently does **not** have `services/llm-gateway/uv.lock`. This is a known repository landmine and is the reason the root `Makefile` uses frozen uv sync for API/worker but normal `uv sync` for the LLM gateway.

Directly audited API lock entries include:

- FastAPI `0.140.13`
- Alembic `1.19.1`

The API manifest also declares SQLAlchemy `>=2,<3`, Pydantic `>=2,<3`, and Uvicorn `>=0.35,<1`.

All three Python services declare development tooling ranges for Ruff, mypy, and pytest in their own `pyproject.toml` files.

### Local infrastructure image versions

The Compose source of truth is `infra/docker/compose.yml`.

Pinned images currently include:

- PostgreSQL + pgvector: `pgvector/pgvector:0.8.6-pg18-bookworm`
- Keycloak: `quay.io/keycloak/keycloak:26.7.1`
- Valkey: `valkey/valkey:8.1.9-alpine`
- S3-compatible object storage: `chrislusf/seaweedfs:4.41`
- Redpanda: `docker.redpanda.com/redpandadata/redpanda:v26.2.1`
- OpenTelemetry Collector: `otel/opentelemetry-collector-contrib:0.153.0`
- Prometheus: `prom/prometheus:v3.13.1`
- Grafana: `grafana/grafana:13.1.0`
- Loki: `grafana/loki:3.7.4`
- Tempo: `grafana/tempo:2.10.7`

No audited local infrastructure image uses a floating `latest` tag.

## 3. Repository map

```text
Serviq/
├── .github/
│   └── workflows/
│       ├── build-4k-designs.yml
│       └── ci.yml
├── apps/
│   ├── client-console/
│   │   └── src/app/
│   ├── customer-web/
│   │   └── src/app/
│   └── platform-console/
│       └── src/app/
├── packages/
│   ├── config/
│   ├── contracts/
│   │   └── src/
│   ├── observability/
│   ├── security/
│   ├── testkit/
│   └── ui/
│       └── src/
├── services/
│   ├── api/
│   │   ├── app/
│   │   └── tests/
│   ├── worker/
│   │   ├── app/
│   │   └── tests/
│   └── llm-gateway/
│       ├── app/
│       └── tests/
├── infra/
│   └── docker/
│       ├── compose.yml
│       ├── postgres/
│       ├── observability/
│       └── README.md
├── docs/
│   ├── ARCHITECTURE.md
│   ├── PRD.md
│   ├── PRODUCT_SPECIFICATION.md
│   ├── TECH_STACK.md
│   ├── SERVIQ_BUILD_GUIDE.md
│   └── contract-changes/
├── Makefile
├── package.json
├── pnpm-workspace.yaml
├── pnpm-lock.yaml
└── .nvmrc
```

Builders must still inspect the exact target subtree before editing. This tree is a navigation map, not a substitute for reading the relevant files.

## 4. Frontend reality

All three frontend applications use the Next.js App Router because their route roots live under `src/app/`.

Current real route examples:

- `apps/client-console/src/app/page.tsx`
- `apps/customer-web/src/app/page.tsx`
- `apps/platform-console/src/app/page.tsx`

These pages are foundation placeholders. They do not represent implemented product workflows.

Current frontend facts:

- strict TypeScript is enabled in app `tsconfig.json` files;
- each app has ESLint configuration;
- Tailwind/PostCSS are configured;
- app-local `dev`, `build`, `lint`, and `typecheck` scripts exist;
- Customer Web and Platform Console include app-local icons added during browser QA;
- no production authentication client exists;
- no real API data-fetch layer exists;
- no form architecture is established;
- no implemented feature-folder convention is demonstrated yet;
- no real support chat, inbox, analytics, or admin workflow exists yet.

The shared UI boundary exists at `packages/ui`.

`packages/ui/src/tokens.css` contains design-token groundwork. `packages/ui/src/index.ts` intentionally does not expose a production component library yet. Therefore builders must not claim there is an existing shared Button, Modal, Table, Form, Toast, or layout component pattern unless a later ticket adds one and this document is re-audited.

## 5. Shared TypeScript package reality

The six shared workspace boundaries are:

- `packages/ui` — shared UI/design-system ownership boundary;
- `packages/contracts` — shared wire-contract boundary;
- `packages/config` — reserved shared configuration boundary;
- `packages/observability` — reserved shared application-telemetry boundary;
- `packages/security` — reserved shared security boundary;
- `packages/testkit` — reserved shared test-support boundary.

A real reusable API contract example exists in `packages/contracts/src/api/envelopes.ts`.

The implemented shared envelope shapes establish:

- success: `{ data, meta? }`
- error: `{ error: { code, message, fields? } }`
- pagination metadata: `page`, `pageSize`, `total`, `totalPages`

`packages/contracts/src/api/correlation.ts` defines the correlation-identifier type.

The auth/event folders inside the contracts package are ownership boundaries, not proof that authentication or durable business-event contracts have been implemented.

## 6. Backend / API reality

### API service

`services/api/app/main.py` currently creates the FastAPI application titled `Serviq API`.

There is still no real production business module demonstrating the planned Router -> Service -> Repository architecture.

The API scaffold contains reserved core files for concerns such as auth, tenancy, idempotency, logging, errors, rate limits, and config. Those files establish ownership locations, not completed subsystems.

There is currently no implemented:

- business REST endpoint;
- database session factory;
- SQLAlchemy model set;
- repository layer;
- tenant middleware;
- authentication middleware/dependency;
- permission guard;
- standardized global exception handler tied to real feature routes;
- health endpoint contract owned by a completed feature ticket.

### Worker service

`services/worker` is a process scaffold with reserved `jobs`, `consumers`, and `core` boundaries.

There is no production broker client, event consumer, retry engine, scheduler, outbox publisher, or business job yet.

### LLM gateway

`services/llm-gateway` creates the `Serviq LLM Gateway` FastAPI application and reserves `adapters`, `routing`, and `schemas` boundaries.

There is no implemented provider integration with OpenAI, Anthropic, Gemini, OpenRouter, or LiteLLM yet. There is no production model routing, fallback, streaming, tenant-secret handling, cost routing, or provider-health logic yet.

## 7. API style reality

The implemented TypeScript contract package establishes the standard envelope vocabulary described above.

The architecture document owns planned `/api/v1` route and API conventions, but the backend still has no real business route proving URL naming, pagination parsing, auth guards, tenant scoping, idempotency behavior, or concrete status-code usage.

Builder rule: do not present architecture prose as an implemented backend example. When the first real feature route lands, this section must be re-audited.

## 8. Authentication and permissions

**Status: not implemented in application code.**

Local identity infrastructure exists through Keycloak in `infra/docker/compose.yml`.

What does not yet exist:

- Serviq realm configuration committed as the production application identity contract;
- real application OIDC client setup;
- permanent local development user model owned by product code;
- frontend login flow;
- token validation middleware;
- role mapping;
- tenant authorization guard;
- permission checks protecting product routes.

`services/api/app/core/auth.py` and `packages/security` are reserved boundaries, not a finished authentication system.

If a later ticket requires auth behavior without an exact contract, record `Needs Architect Decision` instead of inventing token claims, cookie/session semantics, roles, or permissions.

## 9. Database and migration reality

PostgreSQL + pgvector runs locally from `infra/docker/compose.yml`, and `infra/docker/postgres/init-vector.sql` enables the vector extension.

The API has SQLAlchemy and Alembic dependencies available, but there is currently no application schema foundation demonstrating:

- SQLAlchemy engine/session setup;
- base model convention;
- tenant table pattern;
- real repository implementation;
- Alembic environment;
- committed application migration history;
- row-level-security policy implementation.

Migration command: **not implemented yet**.

Needs Architect Decision: any ticket attempting to create application tables before the dedicated database/migration contract establishes the exact implementation pattern.

## 10. Local infrastructure reality

The Compose source of truth is `infra/docker/compose.yml`.

Core local dependencies currently include:

- PostgreSQL + pgvector;
- Keycloak;
- Valkey;
- S3-compatible object storage.

Optional profile `events` includes Redpanda.

The broker advertises an internal Compose Kafka endpoint at `redpanda:9092`. OPE-266 intentionally creates no Serviq business topic, producer, consumer, schema registry, or event payload implementation.

Optional profile `observability` includes:

- OpenTelemetry Collector;
- Prometheus;
- Grafana;
- Loki;
- Tempo.

Observability config is under `infra/docker/observability/`.

Prometheus is currently wired only to its local baseline targets. Grafana provisioning defines Prometheus, Loki, and Tempo data sources. No application telemetry instrumentation, alert rules, or product dashboard is implemented yet.

Validation-only GitHub Actions run `31743262767` proved the optional events and observability profiles can be started independently from the default/core stack. OPE-266 and OPE-267 are now merged into `main`.

## 11. Root developer commands

The root developer command surface is `Makefile`.

Exact required targets currently present:

- `make setup`
- `make dev`
- `make test`
- `make lint`
- `make typecheck`
- `make security`
- `make e2e`
- `make load-test`
- `make down`

Current behavior:

- `setup` installs pnpm dependencies with the existing lockfile, performs frozen uv sync for API and worker, and normal uv sync for LLM gateway because its lockfile is missing;
- `dev` starts the core Compose infrastructure and prints the separate application/service commands instead of inventing an unsupported process supervisor;
- `lint`, `typecheck`, and `test` delegate to the existing pnpm/Python commands;
- `down` stops the Compose project;
- `security`, `e2e`, and `load-test` intentionally exit non-zero until their dedicated tickets implement real gates.

A fake-success placeholder is forbidden because CI must not report a quality gate as green when no real gate ran.

## 12. Testing reality

### JavaScript / frontend

Root scripts recursively call workspace package scripts using pnpm.

The three frontend apps currently provide lint/typecheck/build commands, but there is no established production component/unit-test framework or committed browser E2E suite yet.

### Python

Each Python service has pytest/Ruff/mypy configuration in its `pyproject.toml`.

Real smoke/import tests exist in the service test directories. They validate scaffold integrity, not business behavior.

### E2E and load testing

`make e2e` and `make load-test` deliberately fail because those systems are not implemented yet.

## 13. CI reality

Baseline CI is now implemented at `.github/workflows/ci.yml`.

It triggers on:

- pull requests;
- pushes to `main`.

It uses read-only repository-content permission, a 20-minute job timeout, explicit setup actions for pnpm/Node/Python/uv, and no paid-service secret.

The required gates are:

1. `make setup`
2. `make lint`
3. `make typecheck`
4. `make test`
5. Docker Compose configuration validation

GitHub Actions run `31778357529` passed the complete workflow on the final OPE-269 branch before PR #62 merged into `main`.

The older design workflow remains at `.github/workflows/build-4k-designs.yml` and was not modified by OPE-269.

## 14. File storage reality

S3-compatible local object storage exists through SeaweedFS in the Docker stack.

This is infrastructure only. There is no implemented production file-upload workflow, presigned-URL contract, MIME/extension/size validation pipeline, knowledge-ingestion upload API, export writer, or production AWS S3 integration yet.

Future application code should depend on the architecture-owned S3-compatible storage contract, not vendor-specific SeaweedFS behavior.

## 15. Eventing reality

Redpanda provides a Kafka-compatible local broker under the optional `events` profile.

No Serviq topics exist yet. No application service depends on the broker yet. No producer/consumer/event-schema implementation exists yet.

Future event tickets may use `KAFKA_BOOTSTRAP_SERVERS`, but exact topic names and payload contracts remain architecture-owned.

## 16. Observability reality

The local telemetry infrastructure exists, but application instrumentation does not.

Do not confuse “Grafana/Loki/Tempo/Prometheus/OTel Collector containers are available” with “Serviq application traces, logs, metrics, SLOs, dashboards, or alerts exist.” They do not yet.

`packages/observability` is also only a shared package boundary at this stage.

## 17. Security reality

Current real security foundations include:

- separate public/tenant/platform frontend applications;
- local Keycloak infrastructure;
- reserved `packages/security` ownership boundary;
- API auth/tenancy/idempotency/rate-limit core boundary files;
- local services bound/configured for development rather than treated as production deployment settings;
- baseline CI with read-only token permissions.

Not implemented yet:

- user authentication;
- tenant authorization;
- RBAC enforcement;
- provider-secret storage;
- upload security pipeline;
- security scanner CI gate;
- dependency/container/secret scanning;
- production WAF/rate limiting.

The presence of placeholders must never be described as completed protection.

## 18. Reusable utilities and examples

Use these only for the limited patterns they actually prove:

- API envelope types: `packages/contracts/src/api/envelopes.ts`
- correlation identifier: `packages/contracts/src/api/correlation.ts`
- frontend route shell: any current `apps/*/src/app/page.tsx`
- API application root: `services/api/app/main.py`
- LLM gateway application root: `services/llm-gateway/app/main.py`
- worker process scaffold: `services/worker/app/main.py`
- root developer lifecycle: `Makefile`
- local infrastructure: `infra/docker/compose.yml`
- baseline CI: `.github/workflows/ci.yml`

There is no real example yet for a production business route, service class, repository class, database model, authenticated page, tenant guard, background job, event consumer, provider adapter, or production React component library.

## 19. Known landmines / unknowns

1. `services/llm-gateway/uv.lock` is missing. Do not run frozen uv sync for that service until a dedicated dependency decision adds the lockfile.
2. Authentication infrastructure exists locally, but application auth is not implemented.
3. PostgreSQL and Alembic dependencies exist, but application models/migrations/session patterns are not implemented.
4. Architecture defines Router -> Service -> Repository, but no real feature currently demonstrates it.
5. The shared UI package is not yet a production component library.
6. Observability containers exist, but app instrumentation and dashboards do not.
7. Redpanda exists, but no Serviq topics/events/producers/consumers exist.
8. Security/E2E/load-test Make targets intentionally fail and must not be reported as passing gates.
9. The architecture and Premium Product Builder remain the contract source for future implementation decisions that are not demonstrated in repository code.
10. When a future ticket changes repository structure, dependency versions, commands, auth/database/API conventions, CI gates, or reusable patterns, this file must be re-audited in the affected sections.

## 20. Downstream builder start gate

Every implementation ticket after OPE-270 must do the following before coding:

1. read the Linear/GitHub ticket as the exact scope source;
2. inspect `docs/repo_context.md`;
3. inspect the exact target files/directories from the current branch;
4. verify relevant dependency/tool versions from current manifests/lockfiles;
5. identify at least one real existing pattern when one exists;
6. explicitly state when no real pattern exists;
7. stop and record `Needs Architect Decision` when the ticket requires an undefined contract;
8. do not silently implement architecture changes while executing a builder ticket.

## 21. Current test commands

Repository-wide commands:

```bash
make setup
make lint
make typecheck
make test
```

Local infrastructure:

```bash
make dev
make down
```

Intentional non-implemented gates:

```bash
make security
make e2e
make load-test
```

Those three commands are expected to fail until their dedicated tickets replace the placeholders with real implementations.

## 22. Audit conclusion

The repository now has a credible production-oriented foundation: separated frontend surfaces, shared package boundaries, Python service boundaries, local relational/cache/object/identity/event/observability infrastructure, one root developer command surface, and baseline CI.

The repository does **not** yet have the core product runtime: real authentication, tenant permissions, database models/migrations, support chat, knowledge ingestion/retrieval, agent execution, LLM provider routing, policy authorization, refund/order tools, human handoff, analytics, or application observability.

Future builders must preserve this distinction. The safest implementation is the one that starts from what the repository actually contains today rather than what the architecture intends it to contain later.

## OPE-304 release-system convention update

This section records a repository convention added after the original OPE-270 audit. It supplements the audit snapshot instead of pretending the original audited commit already contained these files.

GitHub Releases are now the repository's official public version-history boundary. The permanent release-management files are:

- `.github/release.yml` — generated release-note categories and exclusions;
- `.github/workflows/release.yml` — validated release publishing;
- `docs/RELEASING.md` — operator/versioning policy;
- `.github/pull_request_template.md` — release-impact declaration on every PR;
- `CONTRIBUTING.md` — contributor-facing Semantic Versioning and release rules.

Serviq release tags use `vMAJOR.MINOR.PATCH` with optional prerelease suffixes such as `-alpha.1`, `-beta.1`, and `-rc.1`. Published tags are treated as permanent history and must never be silently moved to different code.

The release workflow supports two permanent publishing paths: an authorized manual GitHub Actions run from `main`, and a semantic-version tag whose commit is already contained in `main`. Both paths execute `make setup`, `make lint`, `make typecheck`, `make test`, and Docker Compose configuration validation before publishing. The workflow intentionally does not claim `make security`, `make e2e`, or `make load-test` are release gates while those targets remain explicit non-zero placeholders.

OPE-304 also contains a one-time idempotent bootstrap for the first prerelease, `v0.1.0-alpha.1`, after the release-system files merge into `main`. That bootstrap creates the release labels, validates the merged code, refuses to overwrite an existing tag/release, and publishes `Serviq v0.1.0-alpha.1 — Platform Foundation` as a prerelease. Later release-system edits detect the existing bootstrap release and leave it unchanged.

Release publishing is not deployment. There is currently no release-triggered production deployment, GHCR container publication, SBOM, signing, provenance/attestation, backport branch, or automatic SemVer calculation. Those remain future reviewed work.

Builder start rule: when a later ticket changes release/versioning behavior, read `.github/workflows/release.yml`, `.github/release.yml`, `docs/RELEASING.md`, and the current PR template/CONTRIBUTING policy before editing. Release governance is repository behavior and must not be inferred from an old architecture snapshot.

### OPE-304 verified release state

The OPE-304 release system has now been exercised successfully, not merely configured. PR #67 merged to `main` at `46a02b53ea9e3340c90d3aa8c5291f7dd15edf07`; baseline CI run `31832353639` and Release workflow run `31832353708` both succeeded. The first repository tag and GitHub Release are `v0.1.0-alpha.1`, with the tag pointing to that exact merge commit and the release marked as a prerelease.

The release labels defined by OPE-304 now exist in GitHub. Future builders should treat the release workflow, generated-release-note configuration, PR release-impact fields, `CONTRIBUTING.md`, and `docs/RELEASING.md` as implemented repository behavior rather than future planning.

