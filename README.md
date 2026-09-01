# Serviq

**Enterprise AI Customer Operations Platform**

Serviq is an open-source portfolio project for building a multi-tenant AI operations layer between customers and businesses. The product direction combines verified knowledge retrieval, customer and order context, policy-controlled tool execution, human escalation, model routing, and operational observability so an AI agent can do more than generate chat replies.

> **Current status:** Serviq is under active development. The repository has the product/architecture foundation, three web application scaffolds, Python service scaffolds, local infrastructure, CI/security gates, and typed platform configuration. The end-to-end customer-operations product is **not production-ready yet**, and unfinished capabilities are not represented here as completed features.

## What Serviq is designed to become

A completed Serviq deployment is intended to connect customer-facing channels to business knowledge, customer/order systems, approved operational tools, AI models, and human support teams. The architecture separates knowledge retrieval from operational actions: answering a policy question is different from changing an address, canceling an order, or issuing a refund. State-changing actions are designed to pass through authentication, policy, confirmation, authorization, execution, and verification boundaries rather than giving an LLM unrestricted system access.

The implementation is intentionally being built in small, reviewable production-foundation tickets. For the exact current repository truth, see [`docs/repo_context.md`](docs/repo_context.md) and the cumulative [`docs/SERVIQ_BUILD_GUIDE.md`](docs/SERVIQ_BUILD_GUIDE.md).

## Repository map

| Path | Purpose |
| --- | --- |
| `apps/client-console` | Client/business support-console web app scaffold |
| `apps/customer-web` | Customer-facing support web app scaffold |
| `apps/platform-console` | Internal Serviq operator-console web app scaffold |
| `services/api` | FastAPI application boundary |
| `services/worker` | Durable background-worker boundary |
| `services/llm-gateway` | LLM-gateway service boundary |
| `packages/*` | TypeScript contracts, clients, UI, configuration, telemetry, and testing package boundaries |
| `infra/docker` | Local PostgreSQL, Keycloak, Valkey, object storage, optional events, and optional observability infrastructure |
| `docs` | Product, architecture, implementation, design, and contract documentation |

## Read the design before the code

The repository is contract-first. These documents explain the intended product and the decisions code must follow:

- [Product Requirements](docs/PRD.md) — users, goals, scope, roles, flows, and success criteria.
- [Product Specification](docs/PRODUCT_SPECIFICATION.md) — detailed product behavior and operational concepts.
- [Architecture](docs/ARCHITECTURE.md) — technology, data, API, security, integration, and system-boundary decisions.
- [Technology Stack](docs/TECH_STACK.md) — approved technology choices and evolution path.
- [Repository Context](docs/repo_context.md) — what is actually implemented today and which code paths own which responsibilities.
- [Serviq Build Guide](docs/SERVIQ_BUILD_GUIDE.md) — cumulative, non-technical explanation of what has been built, how it works, why each change was made, and what remains intentionally unfinished.
- [Design References](docs/design/README.md) — visual/product-design references used by the project.

## Local prerequisites

Install these tools before running the repository:

- **Node.js 24.18.0** — the exact version is stored in [`.nvmrc`](.nvmrc).
- **pnpm 10.15.0**.
- **Python 3.14.x** — CI currently uses Python 3.14.6; backend packages require `>=3.14,<3.15`.
- **uv** for frozen Python environments and commands.
- **Docker Engine / Docker Desktop with Docker Compose v2** for local infrastructure.
- **GNU Make** for the repository command surface.

## Clone and install

```bash
git clone https://github.com/anmolsansi/Serviq.git
cd Serviq
cp .env.example .env
corepack enable
corepack prepare pnpm@10.15.0 --activate
make setup
```

`make setup` installs the frozen pnpm workspace and the API, worker, and LLM-gateway Python environments. The checked-in `.env.example` contains local placeholder values only. Never commit a real `.env` file or replace placeholders in `.env.example` with production credentials.

## Start local infrastructure

The default Docker stack contains PostgreSQL + pgvector, Keycloak, Valkey, and S3-compatible SeaweedFS object storage. Keycloak deliberately requires a local bootstrap password instead of silently falling back to a known password.

```bash
export KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD='serviq-local-change-me'
make dev
```

`make dev` starts the default Docker infrastructure and prints the exact commands for starting application processes. It does **not** silently start every web/backend process in the background.

Optional Docker Compose profiles are available when a ticket needs them:

```bash
# Durable event broker (Redpanda)
docker compose -f infra/docker/compose.yml --profile events up -d

# OpenTelemetry Collector, Prometheus, Grafana, Loki, and Tempo
docker compose -f infra/docker/compose.yml --profile observability up -d

# All optional profiles
docker compose -f infra/docker/compose.yml --profile '*' up -d
```

Stop the local stack, including profiled services, with:

```bash
make down
```

## Start application scaffolds

Run each process in its own terminal when you need it. These commands are the current repository command surface:

```bash
# Business/client console
pnpm --filter @serviq/client-console dev

# Customer-facing web app
pnpm --filter @serviq/customer-web dev

# Internal Serviq platform console
pnpm --filter @serviq/platform-console dev

# API
cd services/api && uv run uvicorn app.main:app --reload

# Worker
cd services/worker && uv run python -m app.main

# LLM gateway
cd services/llm-gateway && uv run uvicorn app.main:app --reload
```

These applications are still foundation scaffolds. Starting them successfully does not imply that authentication, tenant workflows, RAG, order/refund tools, human handoff, analytics, or end-to-end AI support flows are already implemented.

## Validate a change

Use the same high-level commands used by CI:

```bash
make lint
make typecheck
make test
make security
```

`make security` runs the local dependency-audit subset. Pull requests additionally run the repository Security workflow: CodeQL for JavaScript/TypeScript and Python, Gitleaks secret scanning, Trivy filesystem/configuration scanning, and dependency vulnerability audits.

The following commands are intentionally **planned, not implemented yet**, and currently fail rather than pretending coverage exists:

```bash
make e2e
make load-test
```

## Development workflow

Serviq is developed ticket by ticket. The expected flow is:

1. Start from the relevant Linear ticket and the frozen architecture/repository context.
2. Create a dedicated GitHub issue and branch.
3. Push small commits whose messages describe one logical change.
4. Add tests and update the cumulative build/repository documentation.
5. Open a pull request and require CI/security validation before merging.
6. Merge only after the implemented behavior matches the ticket, and is verified; then close/update GitHub and Linear tracking.


Contract changes are not hidden inside feature work. Changes to frozen API, database, configuration, security, or other cross-ticket contracts require an explicit Contract Change Record (CCR) before dependent code is changed.

## Scale statement

Serviq's architecture is being designed so it can evolve toward very large, horizontally scaled deployments. **10 million concurrent connections/users is a long-term architecture target, not a benchmark achieved by this repository.** Registered users, concurrent connected clients, active request throughput, and LLM request rate are different measurements. Serviq will only claim measured capacity after reproducible load tests exist and publish the exact workload and result.

## Demo and company-reference disclaimer

Serviq may use **DoorDash as a reference customer-support/delivery domain** and **Stripe as a separate reference payment-provider domain** when illustrating workflows. These references do not imply affiliation, sponsorship, endorsement, a DoorDash/Stripe integration, or that DoorDash uses Stripe. Demo customers, orders, payments, policies, conversations, and other private/business records are synthetic unless a source is explicitly documented as public and permitted for use.

## Security note

Do not commit credentials, provider keys, customer PII, private company data, or production secrets. Platform configuration uses explicit environment names and secret-bearing values are server-side. Tenant/provider BYOK credentials are intentionally not modeled as global environment variables. Security scanners reduce risk but do not replace code review, threat modeling, access controls, or production security operations.

## License and contribution status

This repository is currently being built as a public engineering/portfolio project. A formal external contribution policy and release/deployment support policy have not yet been published; do not infer production support commitments from the public source code.
