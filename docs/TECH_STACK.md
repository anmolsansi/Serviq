# Serviq Technology Stack

**Status:** Technology baseline v1.0  
**Goal:** Zero-dollar-friendly local development with a clear path to production-scale deployment  

## 1. Stack Principles

The Serviq stack is selected around five constraints:

1. local development should not require paid infrastructure;
2. application code should remain cloud-portable;
3. the platform must support Python-heavy AI/backend development without sacrificing a polished TypeScript frontend;
4. infrastructure choices must have a credible scale-out path;
5. provider-specific dependencies must be isolated behind internal abstractions.

Dependencies must be pinned through lockfiles. Production releases must use reproducible builds and automated dependency/security updates.

## 2. Recommended Repository Model

Serviq will use a monorepo.

```text
Serviq/
  apps/
    client-console/
    customer-web/
    platform-console/
  services/
    api/
    agent/
    knowledge/
    worker/
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

The monorepo gives one review surface for application contracts, infrastructure, docs, frontend, backend, and tests while Serviq is still one product. Logical service boundaries remain explicit so high-throughput components can later be deployed independently.

## 3. Frontend

### 3.1 Core Framework

**Next.js + React + TypeScript**

Used for:

- client operations console;
- customer standalone support experience;
- platform operator console;
- future embeddable widget build pipeline.

### 3.2 UI System

- Tailwind CSS for utility styling;
- accessible headless component primitives;
- Serviq-owned design system in `packages/ui`;
- Storybook for isolated component states;
- icon library with consistent visual language;
- responsive layout from the first implementation.

The product must not become a collection of unstructured copied components. Shared primitives, tokens, forms, tables, dialogs, status indicators, charts, empty states, and permission states belong in the design system.

### 3.3 Client State and Data

- server-first rendering where appropriate;
- TanStack Query for client-side server-state caching/mutations where needed;
- lightweight local state rather than a global store by default;
- Zod schemas for browser-side validation and shared TypeScript contracts where appropriate.

### 3.4 Streaming

- Server-Sent Events as the default mechanism for token/event streaming because customer support is primarily server-to-client streaming;
- WebSockets reserved for flows that require persistent bidirectional real-time behavior.

### 3.5 Frontend Testing

- Vitest for unit/component logic;
- Testing Library for component behavior;
- Playwright for end-to-end workflows;
- accessibility checks integrated into component/e2e suites;
- visual regression testing introduced for critical design-system and workflow screens.

## 4. Backend

### 4.1 Language

**Python**

Primary backend language because Serviq contains retrieval, AI orchestration, provider integrations, ingestion, evaluation, and data-processing workloads where the Python ecosystem is strongest.

### 4.2 API Framework

**FastAPI**

Used for:

- REST APIs;
- OpenAPI contracts;
- async request handling;
- streaming endpoints;
- internal service APIs where HTTP is appropriate.

### 4.3 Validation and Settings

- Pydantic for typed request/domain boundary validation;
- environment-driven configuration with strongly typed settings;
- no secret values committed to Git.

### 4.4 Persistence Layer

- SQLAlchemy for relational access;
- Alembic for schema migrations;
- explicit repositories/data-access boundaries for tenant scoping and testability.

### 4.5 Background Jobs

The platform will distinguish short interactive requests from asynchronous jobs.

Initial worker execution can use Python worker processes over the selected event/broker layer. The application must not depend on an in-process background task for work that must survive process failure.

Examples:

- knowledge crawling;
- parsing;
- embedding;
- indexing;
- analytics aggregation;
- webhook delivery;
- notifications;
- retry/reconciliation jobs.

## 5. LLM and Agent Layer

### 5.1 Provider Gateway

Serviq will expose one internal LLM Gateway contract.

Initial external provider targets:

- OpenAI;
- Anthropic;
- Gemini;
- OpenRouter.

The initial gateway implementation may use a self-hosted compatibility layer such as LiteLLM, wrapped behind Serviq's own interface so the product is not coupled to that project.

The internal gateway contract must support:

- chat/completions-style generation;
- streaming;
- structured outputs;
- embeddings where supported;
- model aliases;
- provider/model routing;
- fallback;
- timeout;
- usage metadata;
- tenant-scoped BYOK credentials;
- error normalization.

### 5.2 Agent Orchestration

Serviq will implement an explicit domain state machine rather than relying on an unconstrained general-purpose agent loop.

The orchestration layer owns:

- state transitions;
- run budgets;
- retrieval;
- tool proposals;
- policy checks;
- approvals;
- provider calls;
- verification;
- escalation.

A third-party graph/agent library may be evaluated later, but core business state transitions must remain expressed in Serviq-owned domain contracts.

### 5.3 Prompt and Configuration Versioning

Prompts and behavioral settings are treated as versioned product configuration, not hard-coded strings scattered through services.

Each agent run stores:

- agent version;
- prompt/config version;
- provider/model alias;
- tool versions;
- policy versions;
- knowledge version identifiers where feasible.

## 6. Primary Database

### 6.1 PostgreSQL

PostgreSQL is the primary source of truth for:

- tenants;
- users/memberships/RBAC;
- agent configuration;
- provider metadata;
- integrations;
- conversations/messages;
- workflow state;
- approvals;
- escalations;
- audit metadata;
- knowledge metadata;
- idempotency keys;
- transactional outbox.

### 6.2 Vector Search

**pgvector** is the local and initial production vector implementation.

Reasons:

- keeps early operational complexity low;
- runs in the existing PostgreSQL environment;
- supports zero-cost local development;
- lets Serviq validate retrieval requirements before introducing another distributed system.

The Retrieval Service must hide pgvector-specific queries behind an internal contract. A dedicated vector engine can be introduced later without changing the agent API.

### 6.3 Lexical / Hybrid Search

Initial implementation:

- PostgreSQL full-text search plus pgvector;
- application-side or query-layer hybrid scoring;
- optional reranking.

Scale path:

- OpenSearch-compatible dedicated search infrastructure when corpus/query volume justifies it.

## 7. Cache and Ephemeral State

**Redis-compatible storage**

Used for:

- response cache;
- semantic cache metadata;
- rate-limit counters;
- hot tenant/agent configuration;
- ephemeral conversation/stream coordination;
- provider health state;
- short-lived locks when unavoidable;
- request deduplication/coalescing.

Redis is never the only durable record of a completed business mutation.

## 8. Event Streaming and Queues

### 8.1 Contract

Serviq uses a Kafka-compatible event contract for durable asynchronous workflows at scale.

### 8.2 Local Development

Use a single-node Kafka-compatible broker that runs comfortably in Docker. Redpanda is a practical local default because it provides the required Kafka-style development surface with low setup overhead.

### 8.3 Production Scale Path

- managed Kafka/MSK or equivalent when deployed to AWS;
- topic partitioning;
- tenant/conversation partition keys;
- consumer groups;
- retry topics;
- dead-letter topics;
- schema version discipline.

### 8.4 Reliability Pattern

Transactional services use a database outbox to ensure domain writes and event publication cannot silently diverge.

## 9. Object Storage

### 9.1 Local

**MinIO or another S3-compatible local object store**

Used for:

- uploaded documents;
- attachments;
- ingestion artifacts;
- exports;
- evaluation artifacts.

### 9.2 AWS Production

**Amazon S3**

Application code talks through an internal object-storage adapter rather than hard-coding S3 semantics throughout domain services.

## 10. Authentication and Identity

### 10.1 Workforce / Client Users

Use an OIDC-compatible identity layer. The local development environment should use an open-source identity provider such as Keycloak so authentication and role flows can be tested without paid SaaS.

### 10.2 End Customers

Customer identity is separate from workforce identity.

Serviq supports:

- anonymous session;
- tenant-signed short-lived customer token;
- future customer OIDC/OAuth integration;
- verified identity escalation for protected actions.

### 10.3 Cloud Evolution

The identity abstraction must permit migration to or integration with managed identity services later without changing authorization domain logic.

## 11. Authorization

- Serviq-owned capability model;
- tenant-scoped RBAC;
- PostgreSQL row-level security as defense in depth where applicable;
- policy checks at service boundaries;
- object-level checks for conversations/queues/actions;
- deny by default.

Authentication provider roles are not treated as the sole source of product authorization truth.

## 12. Observability

### 12.1 Instrumentation Standard

**OpenTelemetry**

Used across frontend/backend/service calls where practical for:

- distributed traces;
- metrics;
- structured correlation.

### 12.2 Local Observability Stack

- Prometheus for metrics;
- Grafana for dashboards;
- Loki for logs;
- Tempo for traces;
- OpenTelemetry Collector for collection/export.

This stack remains optional through Docker profiles for low-resource local development, but production code must always include instrumentation hooks.

### 12.3 Application Logging

- structured JSON;
- stable error codes;
- request/correlation IDs;
- tenant context;
- secret and PII redaction.

## 13. Security Tooling

Public repository CI should include free/open tooling where practical:

- GitHub CodeQL;
- Gitleaks secret scanning;
- dependency vulnerability scanning;
- Trivy for container/filesystem scanning;
- Semgrep or equivalent SAST rules where useful;
- SBOM generation for releases;
- automated license inventory;
- Dependabot/Renovate-style dependency update automation.

Application security requirements include:

- SSRF protections for knowledge crawlers;
- prompt-injection boundaries;
- attachment validation;
- server-side authorization;
- strict CORS configuration;
- request size limits;
- rate limiting;
- secure cookie/token handling;
- secret redaction;
- idempotency for mutations.

## 14. Developer Tooling

### 14.1 Python

- `uv` for environment/package workflow;
- Ruff for formatting/linting;
- mypy for static type checking;
- pytest for tests;
- coverage reporting;
- pre-commit hooks where they improve local feedback.

### 14.2 TypeScript

- pnpm workspaces for JS/TS monorepo packages;
- ESLint;
- TypeScript strict mode;
- Prettier or one agreed formatter;
- Vitest;
- Playwright.

### 14.3 Task Orchestration

Use a simple root-level task runner such as Make/Task plus workspace scripts. Avoid introducing a heavyweight build system until repository size justifies it.

Representative commands:

```bash
make setup
make dev
make test
make lint
make typecheck
make security
make e2e
make load-test
make down
```

## 15. Local Runtime

**Docker Compose** is the required local platform orchestrator.

Recommended local services:

```text
client-console
customer-web
platform-console
api
agent-worker
knowledge-worker
general-worker
postgres + pgvector
redis
kafka-compatible broker
object storage
identity provider
llm gateway
otel collector
prometheus
grafana
loki
tempo
```

Use Docker Compose profiles so contributors can start only the subset required for their current work.

A fully mocked AI/provider mode must exist so the core application and CI can run without paid API calls.

## 16. Production Container Platform

### 16.1 Containers

- Docker/OCI images;
- multi-stage builds;
- non-root runtime users;
- small production images;
- health/readiness endpoints;
- immutable image tags/digests for releases.

### 16.2 Kubernetes

Kubernetes is the target orchestration layer once the system needs horizontal production scaling.

Expected workloads:

- stateless APIs;
- streaming gateway;
- agent workers;
- knowledge workers;
- integration/tool workers;
- scheduled reconciliation jobs.

Stateful production data should prefer managed services rather than self-hosting databases inside the application cluster.

## 17. AWS Production Mapping

Local/open-source components map approximately to:

| Concern | Local | AWS production target |
|---|---|---|
| Edge/CDN | local reverse proxy | CloudFront |
| WAF | local middleware | AWS WAF |
| Load balancing | reverse proxy | ALB/NLB as appropriate |
| Containers | Docker Compose | EKS/ECS depending deployment decision |
| PostgreSQL | local Postgres | RDS/Aurora PostgreSQL |
| Vector | pgvector | PostgreSQL/managed vector path initially |
| Cache | local Redis-compatible | ElastiCache-compatible path |
| Event broker | local Kafka-compatible broker | MSK or equivalent |
| Object storage | MinIO | S3 |
| Secrets | local secret files | Secrets Manager / Parameter Store |
| Observability | OTel + OSS stack | OTel with managed/OSS backend decision |
| DNS | local hosts | Route 53 |

This table describes architectural mapping, not a commitment to incur AWS costs during development.

## 18. Infrastructure as Code

**Terraform** will define cloud infrastructure when AWS deployment begins.

Rules:

- no manually created production-critical resources without IaC representation;
- environment modules for dev/staging/production;
- remote state with locking in cloud environments;
- sensitive outputs protected;
- plan/apply controlled through CI/CD and review.

Kubernetes resources may use Helm/Kustomize after cluster deployment is introduced.

## 19. CI/CD

**GitHub Actions**

Pull-request checks should include:

1. changed-file detection;
2. formatting/lint;
3. type checking;
4. unit tests;
5. backend/frontend integration tests;
6. tenant-isolation/authorization tests;
7. dependency/security scans;
8. secret scan;
9. container build validation when applicable;
10. e2e smoke suite for relevant changes;
11. documentation/link checks;
12. migration validation.

Main/release workflows later add:

- immutable image builds;
- SBOM;
- artifact signing;
- staging deployment;
- smoke tests;
- controlled production promotion;
- rollback support.

## 20. Testing Stack

### 20.1 Backend

- pytest;
- Testcontainers or Docker-backed integration dependencies;
- property-based testing for selected policy/idempotency logic;
- contract fixtures for external providers/tools;
- deterministic fake LLM implementation.

### 20.2 Frontend

- Vitest;
- Testing Library;
- Playwright;
- accessibility automation.

### 20.3 Load / Performance

**k6** as the default load-testing tool.

Scenarios must separately measure:

- REST API throughput;
- concurrent streaming clients;
- conversation creation/message writes;
- cached deterministic responses;
- retrieval throughput;
- agent worker throughput;
- event broker throughput;
- tool-service behavior;
- provider-limited AI flows using controlled mocks.

External LLM calls should not be used to claim internal platform throughput because provider quotas/costs distort the benchmark.

### 20.4 AI Evaluation

Serviq will maintain versioned evaluation datasets for:

- answer correctness;
- source grounding;
- citation correctness;
- refusal/escalation behavior;
- tool selection;
- argument correctness;
- policy compliance;
- hallucination detection;
- regression across agent/model versions.

Evaluation code and expected behavior belong in the repository.

## 21. API Documentation

- OpenAPI is generated from backend contracts;
- Swagger/ReDoc-style developer view in non-production/internal environments as configured;
- public API examples in `docs/`;
- webhook schemas versioned;
- event schemas versioned;
- breaking changes require an ADR and migration plan.

## 22. Data Migration and Schema Discipline

- Alembic migrations checked into Git;
- forward migrations must support rolling deployment when applicable;
- destructive migrations use expand/migrate/contract pattern;
- production data migration jobs are observable and restartable;
- migrations are tested against representative datasets before release.

## 23. Technology Decisions Intentionally Deferred

The following are not frozen until measurements justify them:

- dedicated vector database vendor;
- dedicated OpenSearch cluster timing;
- exact Kubernetes vs ECS production choice for first AWS deployment;
- multi-region database technology;
- dedicated workflow engine;
- API gateway vendor;
- hosted observability vendor;
- service mesh.

These should be selected through ADRs using measured need, not added preemptively.

## 24. Final Baseline

### Application

```text
Frontend:       Next.js + React + TypeScript
Backend:        Python + FastAPI + Pydantic
ORM/Migrations: SQLAlchemy + Alembic
Primary DB:     PostgreSQL
Vector:         pgvector
Cache:          Redis-compatible
Events:         Kafka-compatible broker
Object storage: S3-compatible local storage -> S3
Identity:       OIDC-compatible, Keycloak locally
LLM layer:      Serviq Gateway, initially backed by a self-hosted provider gateway
Observability:  OpenTelemetry + Prometheus/Grafana/Loki/Tempo
Testing:        pytest + Vitest + Playwright + k6
Containers:     Docker + Docker Compose
Cloud IaC:      Terraform
Scale target:   Kubernetes-based horizontal deployment when required
CI/CD:          GitHub Actions
```

This baseline is intentionally production-oriented while preserving a practical, no-mandatory-paid-service local development workflow.
