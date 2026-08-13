# Serviq Repository Context

> Audit ticket: OPE-270  
> Audited branch: `ope-270-repository-audit`  
> Audit source commit before this file: `b7c94fe55db4837ed93e4ea84722b6bf15f480df`  
> Purpose: give later builders a factual map of what exists in the repository today. This file records implemented reality, not architecture wishes.

## 1. Repository snapshot

Serviq is currently a scaffolded multi-application, multi-service monorepo. The repository has three Next.js applications under `apps/`, six TypeScript workspace packages under `packages/`, three Python services under `services/`, local infrastructure under `infra/docker/`, product and architecture documentation under `docs/`, and GitHub Actions under `.github/workflows/`.

The root workspace is defined by `package.json`, `pnpm-workspace.yaml`, `pnpm-lock.yaml`, `.nvmrc`, and the OPE-268 `Makefile`.

Important reality check: most product behavior is **not implemented yet**. The web applications render foundation placeholder pages, the API and LLM gateway expose only FastAPI application objects, the worker is a process scaffold, and the shared cross-cutting packages mostly reserve ownership boundaries for later tickets.

## 2. Exact toolchain and framework versions

### JavaScript and TypeScript

The repository Node version is `24.18.0`, pinned in `.nvmrc`.

The OPE-269 CI branch pins pnpm `10.15.0` in `.github/workflows/ci.yml`. The root `package.json` does not currently declare a `packageManager` field, so builders must not infer a pnpm version from `package.json`.

The audited `pnpm-lock.yaml` resolves the three web applications to these exact versions:

- Next.js `16.2.9` — `pnpm-lock.yaml`, importers `apps/client-console`, `apps/customer-web`, and `apps/platform-console`.
- React `19.2.0` — `pnpm-lock.yaml`.
- React DOM `19.2.0` — `pnpm-lock.yaml`.
- TypeScript `5.9.3` — resolved from the `^5.1.0` manifest range in all three apps and all six shared packages, recorded in `pnpm-lock.yaml`.
- Tailwind CSS `4.3.3` — `pnpm-lock.yaml`.
- `@tailwindcss/postcss` `4.3.3` — `pnpm-lock.yaml`.
- ESLint `9.39.5` — `pnpm-lock.yaml`.
- `eslint-config-next` `16.2.9` — `pnpm-lock.yaml`.
- `@types/node` `24.13.3`, `@types/react` `19.2.18`, and `@types/react-dom` `19.2.4` — `pnpm-lock.yaml`.

The three application manifests are `apps/client-console/package.json`, `apps/customer-web/package.json`, and `apps/platform-console/package.json`.

### Python

All Python services declare Python `>=3.14,<3.15` in their `pyproject.toml` files. The API and worker have committed uv lockfiles at `services/api/uv.lock` and `services/worker/uv.lock`, which normalize Python to `==3.14.*`. The LLM gateway currently has no committed `services/llm-gateway/uv.lock`; its `pyproject.toml` is the only dependency source committed for that service.

The OPE-269 workflow currently selects Python `3.14.6` in `.github/workflows/ci.yml`.

Directly audited exact API lock entries include:

- FastAPI `0.140.13` — `services/api/uv.lock`.
- Alembic `1.19.1` — `services/api/uv.lock`.

The API manifest declares SQLAlchemy `>=2,<3`, Pydantic `>=2,<3`, and Uvicorn `>=0.35,<1` in `services/api/pyproject.toml`. Exact resolved versions remain in `services/api/uv.lock`; builders changing dependency-sensitive behavior must inspect the lock entry before implementation rather than relying only on the declared range.

Development tooling is declared in each Python service's `pyproject.toml`: Ruff `>=0.12,<1`, mypy `>=1.17,<2`, and pytest `>=8.4,<9`.

### Local infrastructure images

The Compose source is `infra/docker/compose.yml`. The audited branch pins:

- PostgreSQL + pgvector: `pgvector/pgvector:0.8.6-pg18-bookworm`.
- Keycloak: `quay.io/keycloak/keycloak:26.7.1`.
- Valkey: `valkey/valkey:8.1.9-alpine`.
- S3-compatible object storage: `chrislusf/seaweedfs:4.41`.
- Optional event broker: `docker.redpanda.com/redpandadata/redpanda:v26.2.1`.
- Optional OpenTelemetry Collector: `otel/opentelemetry-collector-contrib:0.153.0`.
- Optional Prometheus: `prom/prometheus:v3.13.1`.
- Optional Grafana: `grafana/grafana:13.1.0`.
- Optional Loki: `grafana/loki:3.7.4`.
- Optional Tempo: `grafana/tempo:2.10.7`.

No `latest` tag is used in the audited Compose file.

## 3. Repository map

```text
Serviq/
├── .github/
│   └── workflows/
│       ├── build-4k-designs.yml
│       └── ci.yml
├── apps/
│   ├── client-console/
│   │   └── src/app/{layout.tsx,page.tsx,globals.css}
│   ├── customer-web/
│   │   └── src/app/{layout.tsx,page.tsx,globals.css,icon.svg}
│   └── platform-console/
│       └── src/app/{layout.tsx,page.tsx,globals.css,icon.svg}
├── packages/
│   ├── config/
│   ├── contracts/
│   │   └── src/{api,auth,events,index.ts,typecheck.examples.ts}
│   ├── observability/
│   ├── security/
│   ├── testkit/
│   └── ui/
│       └── src/{index.ts,tokens.css}
├── services/
│   ├── api/
│   │   ├── app/{contracts,core,modules,main.py}
│   │   └── tests/test_app_import.py
│   ├── worker/
│   │   ├── app/{consumers,core,jobs,main.py}
│   │   └── tests/
│   └── llm-gateway/
│       ├── app/{adapters,routing,schemas,main.py}
│       └── tests/
├── infra/docker/
│   ├── compose.yml
│   ├── postgres/
│   ├── observability/
│   │   ├── otel-collector.yaml
│   │   ├── prometheus.yml
│   │   ├── loki.yaml
│   │   ├── tempo.yaml
│   │   └── grafana/provisioning/
│   └── README.md
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

The tree above intentionally stops around two to three levels where practical. Builders must inspect the exact target subtree before editing it.

## 4. Frontend reality

All three web applications use the Next.js App Router because their route entry points live under `src/app/`.

A real current route example is `apps/client-console/src/app/page.tsx`. It exports a single `HomePage` React component that renders static Serviq/Client Console foundation text. `apps/customer-web/src/app/page.tsx` and `apps/platform-console/src/app/page.tsx` follow the same scaffold pattern.

There is currently **no implemented feature-folder architecture**, no API data-fetch layer, no authentication client, no form system, no server action convention, and no real shared component usage in the three apps. Those patterns must not be invented by copying architecture prose alone; later tickets must establish them explicitly.

The shared UI package exists at `packages/ui`. `packages/ui/src/tokens.css` contains design-token placeholders, while `packages/ui/src/index.ts` intentionally exposes no production component library yet. Therefore there is currently no real reusable Button, Modal, Table, Form, Toast, or layout component example to copy.

Frontend linting uses each app's `eslint.config.mjs`. TypeScript uses each app's `tsconfig.json`, with strict compilation and the `@/*` alias pointing to `./src/*`.

## 5. Shared TypeScript package reality

The pnpm workspace includes `apps/*` and `packages/*` through `pnpm-workspace.yaml`. Python services are deliberately outside the pnpm workspace.

The six package boundaries are:

- `packages/ui` — shared UI ownership and token boundary; no real component implementation yet.
- `packages/contracts` — shared wire-contract types.
- `packages/config` — reserved shared configuration boundary; no application configuration system implemented yet.
- `packages/observability` — reserved shared telemetry boundary; no application instrumentation implemented yet.
- `packages/security` — reserved shared security boundary; no authentication/authorization implementation yet.
- `packages/testkit` — reserved shared test-support boundary; no full fixture/fake infrastructure implemented yet.

A real reusable contract example exists in `packages/contracts/src/api/envelopes.ts`. It defines `SuccessEnvelope<T, M>`, `ErrorDetail`, `ErrorEnvelope`, and `PaginationMeta`. `packages/contracts/src/api/correlation.ts` defines the correlation identifier type. `packages/contracts/src/auth/` and `packages/contracts/src/events/` are reserved boundaries, not proof that auth or event payload contracts are implemented.

## 6. API and backend reality

### API service

`services/api/app/main.py` currently contains only:

```python
from fastapi import FastAPI

app = FastAPI(title="Serviq API")
```

There is no real business route, router, service class, repository class, database session, middleware stack, error handler, health endpoint, or authentication dependency to copy yet.

`services/api/app/modules/` currently contains only its package marker. Therefore the architecture's future Router -> Service -> Repository layering is **planned but not yet demonstrated in code**.

`services/api/app/core/` reserves explicit boundaries including `auth.py`, `config.py`, `errors.py`, `idempotency.py`, `logging.py`, `rate_limits.py`, and `tenancy.py`. These are scaffold boundary files, not completed subsystems. For example, `services/api/app/core/auth.py` explicitly states that OIDC validation and authorization behavior are intentionally not implemented.

`services/api/app/contracts/` exists as a Python-side contract boundary but does not currently provide a full implemented request/response model convention.

### Worker service

`services/worker/app/main.py` provides a minimal executable scaffold whose `main()` returns success. `services/worker/app/jobs/`, `services/worker/app/consumers/`, and `services/worker/app/core/` reserve future ownership boundaries. There is no broker client, actual consumer, retry engine, scheduler, outbox publisher, or durable job implementation yet.

### LLM gateway

`services/llm-gateway/app/main.py` creates the `Serviq LLM Gateway` FastAPI application. `services/llm-gateway/app/adapters/`, `routing/`, and `schemas/` reserve the provider-neutral boundary. There is no OpenAI, Anthropic, Gemini, OpenRouter, LiteLLM, routing, fallback, streaming, tenant-secret, or model-call implementation yet.

## 7. API contract style

Implemented TypeScript wire-envelope types live in `packages/contracts/src/api/envelopes.ts` and currently establish the shapes:

- success: `{ data, meta? }`;
- error: `{ error: { code, message, fields? } }`;
- pagination metadata: `page`, `pageSize`, `total`, `totalPages`.

The architecture document `docs/ARCHITECTURE.md` owns the planned `/api/v1` route convention and broader API rules, but there is currently no real FastAPI route under `services/api/app/` demonstrating URL naming, HTTP statuses, pagination parsing, idempotency behavior, tenant scoping, or authorization guards.

**Builder rule:** do not present an architecture-only API convention as an implemented backend example. When the first real route ticket lands, this section must be re-audited.

## 8. Authentication and permissions

**Status: not implemented yet.**

Local identity infrastructure exists through the Keycloak service in `infra/docker/compose.yml`, but no realm, application OIDC client, permanent user configuration, frontend login flow, token validation middleware, role mapping, permission guard, or tenant authorization is implemented in application code.

`services/api/app/core/auth.py` explicitly documents this absence. `packages/security` is also only a reserved boundary at this stage.

Any later ticket requiring authenticated behavior must stop if the exact identity contract is not specified. Record `Needs Architect Decision` rather than inventing token claims, roles, cookie behavior, or permission semantics.

## 9. Database and migrations

Local PostgreSQL infrastructure exists in `infra/docker/compose.yml`. The image includes pgvector, and `infra/docker/postgres/init-vector.sql` enables the vector extension for the local database foundation.

`services/api/pyproject.toml` declares SQLAlchemy and Alembic dependencies, but the repository currently has **no implemented application database model set, SQLAlchemy session factory, repository layer, Alembic environment, or migration history** to use as a real example.

Migration command: **not implemented yet**.

Data-model naming, foreign keys, tenant columns, row-level security, and migration patterns described in architecture documents are planned contracts, not current repository examples.

**Needs Architect Decision** if a ticket attempts to create or change application tables before the dedicated database/migration foundation defines the exact implementation pattern.

## 10. Local infrastructure and profiles

The Compose source of truth is `infra/docker/compose.yml`.

Core services currently include PostgreSQL, Keycloak, Valkey, and S3-compatible object storage. The event broker is isolated behind the `events` profile. OpenTelemetry Collector, Prometheus, Grafana, Loki, and Tempo are isolated behind the `observability` profile.

The optional event broker advertises the internal Compose endpoint `redpanda:9092`. OPE-266 intentionally creates no Serviq topic, producer, consumer, or schema registry.

The observability configuration files are under `infra/docker/observability/`. Prometheus currently scrapes itself and the collector only. Grafana provisioning defines Prometheus, Loki, and Tempo data sources. There are no application-specific dashboards or app instrumentation yet.

The OPE-266 and OPE-267 infrastructure changes are stacked branch work at the time of this audit, not yet merged into `main`. Later builders must verify current `main` before assuming those services are available there.

## 11. Root developer commands

The root developer command surface is `Makefile`.

Required targets present on the audited branch:

- `make setup` — frozen pnpm install, frozen uv sync for API and worker, and normal `uv sync` for the LLM gateway because that service currently has no committed lockfile.
- `make dev` — starts core Compose infrastructure and prints that application/service processes should be started separately.
- `make test` — root pnpm tests plus pytest for all three Python services.
- `make lint` — root pnpm lint plus Ruff for all three Python services.
- `make typecheck` — root pnpm typecheck plus mypy for all three Python services.
- `make security` — intentionally not implemented and returns non-zero; references OPE-272.
- `make e2e` — intentionally not implemented and returns non-zero.
- `make load-test` — intentionally not implemented and returns non-zero.
- `make down` — stops the Compose project, enabling all profiles for teardown.

The placeholder targets must continue to fail until their dedicated implementations land. Returning success from a placeholder would create a false CI signal.

## 12. Testing reality

### JavaScript

The root `package.json` delegates `lint`, `typecheck`, and `test` recursively with `pnpm -r --if-present`. Each app has lint/typecheck/build/dev scripts. The current frontend scaffolds do not yet establish a real component/unit-testing framework or browser E2E suite.

### Python

Each Python service configures pytest, Ruff, and strict mypy in its `pyproject.toml`.

A real API smoke test exists at `services/api/tests/test_app_import.py`; it validates that the FastAPI application imports and has the expected title. Worker and LLM-gateway tests are scaffold/smoke-level, not business behavior tests.

### E2E and load testing

`make e2e` and `make load-test` intentionally fail because those systems are not implemented yet.

## 13. CI reality

The pre-existing design workflow is `.github/workflows/build-4k-designs.yml`.

The OPE-269 branch adds `.github/workflows/ci.yml` with read-only `contents` permission, a 20-minute timeout, pinned major action versions, Node/pnpm setup, Python/uv setup, dependency caching, `make setup`, `make lint`, `make typecheck`, `make test`, and a separate Compose-model validation step.

**Validated state:** the OPE-269 workflow triggers on pull requests and pushes to `main`. GitHub Actions run `31743372387` completed successfully on the rebased branch and passed dependency setup, lint, typecheck, test, and Compose configuration validation. An earlier run exposed the missing LLM-gateway lockfile assumption in `make setup`; OPE-268 was corrected to use the dependency state that actually exists in the repository.

There is no CodeQL, Gitleaks, Trivy, Playwright, k6, Docker image publishing, deployment, or release gate in baseline CI yet.

## 14. Reusable utilities and patterns that really exist

Safe existing examples builders may inspect:

- API envelope types: `packages/contracts/src/api/envelopes.ts`.
- Correlation identifier type: `packages/contracts/src/api/correlation.ts`.
- UI token boundary: `packages/ui/src/tokens.css`.
- Next.js root page scaffold: `apps/client-console/src/app/page.tsx`.
- FastAPI app construction: `services/api/app/main.py` and `services/llm-gateway/app/main.py`.
- Worker executable boundary: `services/worker/app/main.py`.
- Python quality-tool configuration: each service's `pyproject.toml`.
- Local infrastructure service style: `infra/docker/compose.yml`.
- Observability provisioning: `infra/docker/observability/**`.
- Root quality command delegation: `Makefile`.

Do not treat empty/reserved packages as reusable implementations merely because their directories exist.

## 15. Naming and structural conventions observed

Observed, not guessed:

- Frontend application directories use kebab-case: `client-console`, `customer-web`, `platform-console`.
- Shared pnpm packages use the `@serviq/*` scope.
- Python package directories use snake_case module filenames such as `rate_limits.py` and `idempotency.py`.
- Docker Compose service names use kebab-case where multiple words are needed, such as `object-storage` and `otel-collector`.
- Infrastructure configuration lives under `infra/docker/` rather than inside application directories.
- Long-form implementation explanation lives in the cumulative `docs/SERVIQ_BUILD_GUIDE.md`; separate long-form per-ticket worklogs are not the repository convention.

## 16. Unknowns and landmines

1. **The LLM gateway has no committed uv lockfile.** `make setup` therefore uses normal `uv sync` for `services/llm-gateway` while API and worker use `--frozen`. This is an explicit reproducibility landmine; future dependency-hardening work should either commit a reviewed gateway lockfile or deliberately document a different dependency policy.
2. **OPE-266 runtime acceptance was exercised in GitHub Actions run `31743262767`.** The default profile started without Redpanda, the events profile reached the point where `rpk cluster info` and `rpk topic list` succeeded, and stopping Redpanda left the core services running.
3. **OPE-267 runtime startup was exercised in GitHub Actions run `31743262767`.** The optional services were absent from the default profile and all five observability services started under the `observability` profile. This audit does not overclaim an independent Grafana datasource-health API or Prometheus-target assertion beyond that startup/provisioning evidence.
4. **Authentication is not implemented.** Keycloak infrastructure does not equal application authentication. See `services/api/app/core/auth.py`.
5. **Database application patterns are not implemented.** SQLAlchemy/Alembic dependencies do not equal models, sessions, repositories, or migrations.
6. **No real Router -> Service -> Repository example exists yet.** Later backend tickets must establish this without pretending the empty `services/api/app/modules/` directory is an implementation.
7. **No real frontend feature-folder/data-fetch pattern exists yet.** All three apps are still root-page scaffolds.
8. **No product telemetry instrumentation exists.** Local observability infrastructure must not be confused with traces/metrics/logs emitted by Serviq applications.
9. **No event payload/topic contract exists in code.** The Redpanda service must not be used as justification to invent topic names or payload schemas.
10. **Root README is intentionally minimal.** `README.md` is not yet a contributor runbook.
11. **Current branch stacking matters.** OPE-267, OPE-268, OPE-269, and this audit are based on preceding ticket branches. Verify `main` before starting downstream work.

## 17. Builder start gate

Every ticket after OPE-270 must perform these checks before editing code:

1. Read this `docs/repo_context.md`.
2. Fetch the current target branch or `main`; do not assume this audit commit is still current.
3. Confirm every path named by the ticket exists.
4. Inspect at least one real implementation example in the affected area. If none exists, state that explicitly.
5. Compare the ticket's API/data/auth/security assumptions with current code. If a required contract is missing, stop and write `Needs Architect Decision: ...`.
6. Reuse the exact root commands from `Makefile` for setup, lint, typecheck, and tests.
7. Do not claim placeholder `security`, `e2e`, or `load-test` gates pass until their dedicated implementations replace the intentional non-zero targets.
8. If a structural convention changes, update this file in the same architectural change or immediately re-audit the affected section.

## 18. Audit conclusion

The repository has a coherent production-oriented **foundation**, but it is still primarily scaffolding. The strongest implemented contracts today are repository boundaries, dependency/tooling versions, shared API envelope types, local infrastructure boundaries, and quality-command conventions. Authentication, application database patterns, real business routes, real frontend features, provider routing, durable consumers, E2E tests, load tests, and security scanning remain future work.

This distinction is mandatory for downstream builders: use real files as evidence, mark unknowns explicitly, and never convert architecture intent into a claim that code already exists.
