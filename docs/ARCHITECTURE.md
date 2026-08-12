# Architecture Plan: Serviq — Production V1

**Status:** Architecture baseline v1.1  
**Scope:** Production V1 defined by `docs/PRD.md`  
**Architecture rule:** Builders implement frozen contracts. Contract changes require the procedure in the premium-product-builder contract-change rules and an ADR/CCR before implementation changes.  
**Scale statement:** The design preserves a path toward millions of concurrent users and a long-term 10M concurrent-connection target. Neither 10M concurrency nor 10M RPS is a verified claim until reproducible tests prove it.

## 1. Stack Decisions

The version baseline below is the initial scaffold target. Exact patch versions must be locked in repository lockfiles and recorded in `docs/repo_context.md` after scaffolding. Security patches supersede this table when required.

| Layer | Choice | Reason |
|---|---|---|
| Frontend | Next.js 16.2.x Active LTS + React 19.2 + TypeScript strict | Mature React platform, server rendering, route handlers, streaming support, and a strong production ecosystem. |
| Frontend forms | react-hook-form + Zod | Explicit form state and one schema vocabulary for browser validation. |
| Frontend server state | TanStack Query where client-side fetching/mutations are required | Keeps server state out of local component state and supports predictable invalidation. |
| Styling/design system | Tailwind CSS + Serviq-owned accessible primitives in `packages/ui` | Fast local development without coupling product UX to a proprietary component vendor. |
| Backend language | Python 3.14.x | Strong AI/data ecosystem and mature async/runtime tooling. |
| API framework | FastAPI 0.140.x + Pydantic 2.x | Typed request boundaries, OpenAPI generation, async I/O, and SSE support. |
| ORM/migrations | SQLAlchemy 2.x + Alembic | Explicit relational access and production migration discipline. |
| Primary database | PostgreSQL 18.x | Transactional source of truth, row-level security, full-text search, and native UUIDv7 support. |
| Vector search | pgvector in PostgreSQL | Keeps V1 operational complexity low while Retrieval Service hides the implementation. |
| Cache/ephemeral | Valkey 8.x-compatible client/protocol | Open Redis-compatible cache for sessions, counters, cache, and coordination. Never source of truth. |
| Event broker | Kafka-compatible contract. Redpanda local profile. Managed Kafka/MSK scale path. | Durable asynchronous work, partitioning, consumer groups, retries, and outbox integration. |
| Object storage | MinIO/S3-compatible local adapter. Amazon S3 production mapping. | Free local storage with cloud-portable object semantics. |
| Workforce auth | Keycloak 26.7.x OIDC for local/dev. OIDC abstraction for production. | Free standards-based identity with a path to managed identity later. |
| Workforce session | Authorization Code + PKCE. Server-managed session. `HttpOnly`, `Secure` in production, `SameSite=Lax` cookie. | Keeps access/refresh tokens out of localStorage and browser JavaScript. |
| LLM gateway | Serviq-owned provider-neutral interface with a self-hosted LiteLLM-compatible gateway adapter | BYOK support across OpenAI, Anthropic, Gemini, and OpenRouter without provider SDK types leaking into domain code. |
| Observability | OpenTelemetry + Prometheus + Grafana + Loki + Tempo | Free local traces, metrics, and logs with standard instrumentation. |
| Local orchestration | Docker Compose profiles | One-command local development without paid infrastructure. |
| Production containers | OCI/Docker images. Kubernetes is the scale target after measured need. | Horizontal stateless scaling and worker separation while avoiding premature cluster dependency during local development. |
| IaC | Terraform when AWS deployment begins | Reviewable, reproducible infrastructure. |
| CI/CD | GitHub Actions | Native repository automation for tests, security, artifacts, and release gates. |
| Load testing | k6 | Reproducible API and concurrent streaming scenarios with machine-readable results. |

## 2. Frontend Architecture

### 2.1 Applications

```text
apps/
  client-console/
    src/
      app/
      features/
      components/
      lib/
  customer-web/
    src/
      app/
      features/
      components/
      lib/
  platform-console/
    src/
      app/
      features/
      components/
      lib/
packages/
  ui/
  contracts/
  config/
  observability/
  security/
  testkit/
```

- `client-console` contains tenant onboarding, configuration, analytics, conversations, and the human support workspace.
- `customer-web` contains the standalone customer support experience and the reference implementation used by an embeddable channel later.
- `platform-console` is a separate Serviq operator surface and never reuses tenant authorization as a substitute for platform authorization.

### 2.2 Routing

Next.js App Router is used. Feature areas are route groups, but authorization is enforced by the API and session boundary, not by hidden navigation alone.

Representative client routes:

```text
/onboarding
/overview
/conversations
/conversations/[conversationId]
/support
/support/[escalationId]
/knowledge/sources
/knowledge/documents
/knowledge/retrieval-debugger
/agents
/agents/[agentId]
/providers
/tools
/policies
/analytics
/audit
/team
/settings
```

Customer routes:

```text
/support/[tenantSlug]
/support/[tenantSlug]/conversations/[conversationId]
```

Platform routes:

```text
/tenants
/health
/providers
/queues
/jobs
/incidents
/feature-flags
/rate-limits
/usage
/security
```

### 2.3 Feature Folder Contract

Every frontend feature follows:

```text
src/features/[feature]/
  components/
  hooks/
  api.ts
  types.ts
  schemas.ts
```

Cross-feature imports are prohibited. Shared UI is placed in `packages/ui`. Shared API contracts are generated or mirrored from `packages/contracts` rather than invented by components.

### 2.4 State and Data Fetching

- Server data is fetched through server components/route handlers when that improves security or page loading, and through TanStack Query for interactive client-side data.
- Server data is never copied into `useState` simply to mirror query results.
- Local UI state stays in components or feature hooks.
- No global client store is introduced in V1 unless an ADR and ticket name the exact state.
- Forms use react-hook-form + Zod with validation rules matching server contracts exactly.
- All client API calls go through the feature `api.ts` and a shared authenticated client. Inline `fetch` in components is prohibited.

### 2.5 Mandatory UI States

Every data-driven screen implements:

1. loading with skeleton/spinner;
2. empty with plain-language explanation and next action;
3. error with safe message and retry where safe;
4. permission denied where relevant;
5. success state;
6. mutation pending and mutation success/failure feedback.

### 2.6 Accessibility and Responsive Rules

- WCAG 2.1 AA practices are the V1 target.
- Mobile-first layouts. No horizontal page scroll at 375 px.
- Inputs require labels. Icon buttons require `aria-label`.
- Dialogs trap focus and close on Escape unless doing so would discard a protected confirmation without warning.
- Support conversation remains keyboard operable and screen-reader understandable during streaming.

## 3. Backend Architecture

### 3.1 Initial Deployment Shape

V1 starts as a **modular monolith plus durable workers**, not 15 independently deployed microservices. The module seams below are contracts that can be extracted later without changing external behavior.

```text
services/
  api/
    app/
      main.py
      core/
        config.py
        errors.py
        logging.py
        auth.py
        tenancy.py
        idempotency.py
      modules/
        tenants/
        providers/
        agents/
        knowledge/
        retrieval/
        conversations/
        tools/
        policies/
        support/
        analytics/
        audit/
        platform_ops/
      contracts/
  worker/
    app/
      jobs/
      consumers/
      core/
  llm-gateway/
    app/
      adapters/
      routing/
      schemas/
```

Each Python module uses:

```text
router.py -> service.py -> repository.py -> database
schemas.py        # Pydantic request/response/domain boundary models
models.py         # SQLAlchemy models
permissions.py    # named capabilities used by guards/service entry
errors.py         # module domain errors if needed
```

### 3.2 Layering

- **Router:** validates path/query/body/header inputs, declares auth, calls one service operation, and maps the result to the API contract.
- **Service:** owns business rules, transactions, policy orchestration, and domain decisions. No FastAPI request/response objects.
- **Repository:** owns SQL/ORM queries. No business decisions.
- Modules call exported service interfaces, never another module's repository.

### 3.3 Validation

- Pydantic validates bodies and structured headers.
- Path/query values are typed and constrained at the router boundary.
- Unknown body fields are rejected.
- File name, extension, MIME type, size, source URL, webhook payload, and model-generated structured output are validated server-side.

### 3.4 Error Handling

One global exception handler converts typed domain errors to the API error envelope in Section 5. Unexpected exceptions are logged with correlation context and return a generic `INTERNAL_ERROR` response with no internal stack or secret data.

### 3.5 Configuration

Configuration is environment-driven and typed. No business/config constants are hardcoded in feature code when they belong to environment or tenant configuration. Secret values are loaded only in server processes and never serialized to clients.

## 4. Database Architecture

### 4.1 Conventions

- PostgreSQL 18.x.
- Table/column names are plural/snake_case.
- Primary keys are UUID with `DEFAULT uuidv7()`.
- Unless a table is explicitly append-only, every table has `created_at timestamptz NOT NULL DEFAULT now()` and `updated_at timestamptz NOT NULL DEFAULT now()`.
- Tenant-owned tables have `tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT` and an index beginning with `tenant_id`.
- Foreign keys are indexed.
- Nullable columns are nullable only when the state model requires them.
- Money is integer cents plus ISO currency code.
- Status/type values use `text` with CHECK constraints in V1 to reduce enum migration friction.
- Multi-table writes use a transaction. No external HTTP/LLM call runs inside a database transaction.

### 4.2 V1 Tables

The schema below is the architectural contract. Ticket-level migrations may split creation across MASs but may not rename or repurpose fields without contract change control.

```text
tenants
  id uuid PK DEFAULT uuidv7()
  slug text NOT NULL UNIQUE CHECK length 3..63
  display_name text NOT NULL CHECK length 1..120
  status text NOT NULL CHECK active|suspended|deleted
  default_locale text NOT NULL DEFAULT 'en'
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Indexes: UNIQUE(slug); (status)

users
  id uuid PK DEFAULT uuidv7()
  oidc_issuer text NOT NULL
  oidc_subject text NOT NULL
  email text NOT NULL
  display_name text NOT NULL
  status text NOT NULL CHECK active|disabled
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(oidc_issuer, oidc_subject)
Indexes: (email)

memberships
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  user_id uuid NOT NULL FK users RESTRICT
  status text NOT NULL CHECK invited|active|suspended
  invited_by uuid NULL FK users RESTRICT
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(tenant_id, user_id)
Indexes: (tenant_id, status); (user_id)

roles
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NULL FK tenants RESTRICT
  key text NOT NULL CHECK length 2..64
  display_name text NOT NULL CHECK length 1..80
  is_system boolean NOT NULL DEFAULT false
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE NULLS NOT DISTINCT(tenant_id, key)
Indexes: (tenant_id)

role_permissions
  id uuid PK DEFAULT uuidv7()
  role_id uuid NOT NULL FK roles CASCADE
  permission_key text NOT NULL CHECK length 2..120
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(role_id, permission_key)
Indexes: (role_id)

membership_roles
  id uuid PK DEFAULT uuidv7()
  membership_id uuid NOT NULL FK memberships CASCADE
  role_id uuid NOT NULL FK roles RESTRICT
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(membership_id, role_id)
Indexes: (membership_id); (role_id)

provider_connections
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  provider text NOT NULL CHECK openai|anthropic|gemini|openrouter
  display_name text NOT NULL CHECK length 1..80
  secret_ref text NOT NULL
  status text NOT NULL CHECK untested|active|invalid|disabled
  last_tested_at timestamptz NULL
  last_error_code text NULL
  created_by uuid NOT NULL FK users RESTRICT
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(tenant_id, display_name)
Indexes: (tenant_id, provider, status)

model_configurations
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  provider_connection_id uuid NOT NULL FK provider_connections RESTRICT
  alias text NOT NULL CHECK length 1..80
  upstream_model text NOT NULL CHECK length 1..160
  purpose text NOT NULL CHECK generation|embedding|rerank
  enabled boolean NOT NULL DEFAULT true
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(tenant_id, alias)
Indexes: (tenant_id, purpose, enabled); (provider_connection_id)

agents
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  name text NOT NULL CHECK length 1..100
  status text NOT NULL CHECK active|archived
  created_by uuid NOT NULL FK users RESTRICT
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(tenant_id, name)
Indexes: (tenant_id, status)

agent_versions
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  agent_id uuid NOT NULL FK agents RESTRICT
  version integer NOT NULL CHECK version > 0
  status text NOT NULL CHECK draft|published|retired
  config jsonb NOT NULL
  config_schema_version integer NOT NULL DEFAULT 1
  published_by uuid NULL FK users RESTRICT
  published_at timestamptz NULL
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(agent_id, version)
Indexes: (tenant_id, agent_id, status)

agent_deployments
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  agent_id uuid NOT NULL FK agents RESTRICT
  agent_version_id uuid NOT NULL FK agent_versions RESTRICT
  channel text NOT NULL CHECK customer_web
  status text NOT NULL CHECK active|paused
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(tenant_id, channel)
Indexes: (tenant_id, status); (agent_version_id)

knowledge_sources
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  source_type text NOT NULL CHECK url|sitemap|pdf|markdown|text
  name text NOT NULL CHECK length 1..160
  source_uri text NULL
  object_key text NULL
  access_scope text NOT NULL CHECK customer|internal
  status text NOT NULL CHECK pending|syncing|ready|failed|disabled
  sync_version integer NOT NULL DEFAULT 0
  last_synced_at timestamptz NULL
  last_error_code text NULL
  created_by uuid NOT NULL FK users RESTRICT
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: URL/sitemap requires source_uri; file types require object_key
Indexes: (tenant_id, status); (tenant_id, source_type)

knowledge_documents
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  source_id uuid NOT NULL FK knowledge_sources RESTRICT
  canonical_uri text NULL
  title text NOT NULL DEFAULT ''
  content_hash text NOT NULL
  document_version integer NOT NULL
  status text NOT NULL CHECK active|deprecated|failed
  fetched_at timestamptz NULL
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(source_id, canonical_uri, document_version)
Indexes: (tenant_id, source_id, status); (content_hash)

knowledge_chunks
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  document_id uuid NOT NULL FK knowledge_documents CASCADE
  ordinal integer NOT NULL CHECK ordinal >= 0
  content text NOT NULL
  token_count integer NOT NULL CHECK token_count >= 0
  metadata jsonb NOT NULL DEFAULT '{}'
  embedding vector NULL
  embedding_model_alias text NULL
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(document_id, ordinal)
Indexes: (tenant_id, document_id); GIN(tsv); vector index is added only after one V1 embedding dimension is frozen by ADR

customers
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  external_ref text NULL
  display_name text NULL CHECK length <= 120
  email text NULL
  status text NOT NULL CHECK active|blocked
  metadata jsonb NOT NULL DEFAULT '{}'
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE NULLS NOT DISTINCT(tenant_id, external_ref)
Indexes: (tenant_id, email); (tenant_id, status)

customer_identities
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  customer_id uuid NOT NULL FK customers CASCADE
  issuer text NOT NULL
  subject text NOT NULL
  assurance_level text NOT NULL CHECK anonymous|verified
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(tenant_id, issuer, subject)
Indexes: (tenant_id, customer_id)

conversations
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  customer_id uuid NULL FK customers RESTRICT
  agent_deployment_id uuid NOT NULL FK agent_deployments RESTRICT
  status text NOT NULL CHECK open|pending|escalated|resolved|reopened
  channel text NOT NULL CHECK customer_web
  current_owner_type text NOT NULL CHECK ai|human
  last_message_at timestamptz NOT NULL DEFAULT now()
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Indexes: (tenant_id, status, last_message_at DESC); (tenant_id, customer_id, last_message_at DESC)

messages
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  conversation_id uuid NOT NULL FK conversations CASCADE
  sequence bigint NOT NULL CHECK sequence > 0
  actor_type text NOT NULL CHECK customer|ai|tenant_user|system
  actor_id uuid NULL
  visibility text NOT NULL CHECK customer|internal
  content_type text NOT NULL CHECK text|status|action_card
  content text NOT NULL DEFAULT ''
  metadata jsonb NOT NULL DEFAULT '{}'
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(conversation_id, sequence)
Indexes: (tenant_id, conversation_id, sequence)

agent_runs
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  conversation_id uuid NOT NULL FK conversations CASCADE
  trigger_message_id uuid NOT NULL FK messages RESTRICT
  agent_version_id uuid NOT NULL FK agent_versions RESTRICT
  status text NOT NULL CHECK queued|running|completed|escalated|failed|budget_exhausted
  request_class text NULL CHECK deterministic|knowledge|transactional|reasoning|escalation_first
  step_count integer NOT NULL DEFAULT 0
  model_call_count integer NOT NULL DEFAULT 0
  tool_call_count integer NOT NULL DEFAULT 0
  started_at timestamptz NULL
  completed_at timestamptz NULL
  failure_code text NULL
  correlation_id text NOT NULL
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Indexes: (tenant_id, conversation_id, created_at DESC); (tenant_id, status, created_at)

agent_steps
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  agent_run_id uuid NOT NULL FK agent_runs CASCADE
  ordinal integer NOT NULL CHECK ordinal >= 0
  step_type text NOT NULL
  status text NOT NULL CHECK started|completed|failed|skipped
  input_summary jsonb NOT NULL DEFAULT '{}'
  output_summary jsonb NOT NULL DEFAULT '{}'
  started_at timestamptz NOT NULL DEFAULT now()
  completed_at timestamptz NULL
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(agent_run_id, ordinal)
Indexes: (tenant_id, agent_run_id, ordinal)

retrieval_runs
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  agent_run_id uuid NOT NULL FK agent_runs CASCADE
  query_text text NOT NULL
  top_k integer NOT NULL CHECK top_k BETWEEN 1 AND 50
  status text NOT NULL CHECK completed|failed
  duration_ms integer NOT NULL CHECK duration_ms >= 0
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Indexes: (tenant_id, agent_run_id, created_at)

retrieval_results
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  retrieval_run_id uuid NOT NULL FK retrieval_runs CASCADE
  chunk_id uuid NOT NULL FK knowledge_chunks RESTRICT
  rank integer NOT NULL CHECK rank > 0
  lexical_score double precision NULL
  vector_score double precision NULL
  final_score double precision NOT NULL
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(retrieval_run_id, rank); UNIQUE(retrieval_run_id, chunk_id)
Indexes: (tenant_id, retrieval_run_id, rank)

tools
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  key text NOT NULL CHECK length 2..120
  display_name text NOT NULL CHECK length 1..120
  status text NOT NULL CHECK active|disabled
  risk_class text NOT NULL CHECK read_only|low|medium|high
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(tenant_id, key)
Indexes: (tenant_id, status)

tool_versions
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  tool_id uuid NOT NULL FK tools RESTRICT
  version integer NOT NULL CHECK version > 0
  input_schema jsonb NOT NULL
  output_schema jsonb NOT NULL
  implementation_key text NOT NULL
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(tool_id, version)
Indexes: (tenant_id, tool_id, version DESC)

policies
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  key text NOT NULL CHECK length 2..120
  display_name text NOT NULL CHECK length 1..120
  status text NOT NULL CHECK active|disabled
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(tenant_id, key)
Indexes: (tenant_id, status)

policy_versions
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  policy_id uuid NOT NULL FK policies RESTRICT
  version integer NOT NULL CHECK version > 0
  rules jsonb NOT NULL
  created_by uuid NOT NULL FK users RESTRICT
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(policy_id, version)
Indexes: (tenant_id, policy_id, version DESC)

tool_executions
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  agent_run_id uuid NOT NULL FK agent_runs RESTRICT
  tool_version_id uuid NOT NULL FK tool_versions RESTRICT
  policy_version_id uuid NULL FK policy_versions RESTRICT
  idempotency_key text NOT NULL
  status text NOT NULL CHECK proposed|blocked|pending_confirmation|pending_approval|executing|succeeded|failed|unknown
  input jsonb NOT NULL
  normalized_output jsonb NULL
  external_operation_ref text NULL
  failure_code text NULL
  started_at timestamptz NULL
  completed_at timestamptz NULL
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(tenant_id, idempotency_key)
Indexes: (tenant_id, agent_run_id, created_at); (tenant_id, status, created_at)

action_confirmations
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  tool_execution_id uuid NOT NULL FK tool_executions RESTRICT
  customer_id uuid NULL FK customers RESTRICT
  status text NOT NULL CHECK pending|confirmed|declined|expired
  expires_at timestamptz NOT NULL
  decided_at timestamptz NULL
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(tool_execution_id)
Indexes: (tenant_id, status, expires_at)

approvals
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  tool_execution_id uuid NOT NULL FK tool_executions RESTRICT
  status text NOT NULL CHECK pending|approved|rejected|expired
  requested_by_type text NOT NULL CHECK customer|ai|tenant_user|system
  requested_by_id uuid NULL
  approver_user_id uuid NULL FK users RESTRICT
  reason text NOT NULL DEFAULT ''
  expires_at timestamptz NOT NULL
  decided_at timestamptz NULL
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(tool_execution_id)
Indexes: (tenant_id, status, expires_at); (tenant_id, approver_user_id, status)

support_queues
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  name text NOT NULL CHECK length 1..100
  status text NOT NULL CHECK active|disabled
  sla_first_response_minutes integer NOT NULL CHECK > 0
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(tenant_id, name)
Indexes: (tenant_id, status)

escalations
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  conversation_id uuid NOT NULL FK conversations RESTRICT
  queue_id uuid NOT NULL FK support_queues RESTRICT
  status text NOT NULL CHECK open|assigned|resolved|reopened
  priority text NOT NULL CHECK low|normal|high|urgent
  reason_code text NOT NULL
  handoff_summary jsonb NOT NULL
  assigned_user_id uuid NULL FK users RESTRICT
  first_response_due_at timestamptz NOT NULL
  resolved_at timestamptz NULL
  resolution_code text NULL
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Indexes: (tenant_id, queue_id, status, priority, created_at); (tenant_id, assigned_user_id, status)

internal_notes
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  conversation_id uuid NOT NULL FK conversations CASCADE
  author_user_id uuid NOT NULL FK users RESTRICT
  content text NOT NULL CHECK length BETWEEN 1 AND 10000
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Indexes: (tenant_id, conversation_id, created_at)

feedback
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  conversation_id uuid NOT NULL FK conversations CASCADE
  customer_id uuid NULL FK customers RESTRICT
  rating smallint NOT NULL CHECK rating BETWEEN 1 AND 5
  comment text NULL CHECK length <= 2000
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Indexes: (tenant_id, created_at); (tenant_id, conversation_id)

usage_events
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  event_type text NOT NULL
  dimensions jsonb NOT NULL DEFAULT '{}'
  quantity bigint NOT NULL DEFAULT 1
  amount_microusd bigint NULL CHECK amount_microusd >= 0
  occurred_at timestamptz NOT NULL
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Indexes: (tenant_id, event_type, occurred_at)

audit_events
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NULL FK tenants RESTRICT
  actor_type text NOT NULL CHECK customer|tenant_user|service|platform_operator
  actor_id text NOT NULL
  action text NOT NULL
  resource_type text NOT NULL
  resource_id text NOT NULL
  outcome text NOT NULL CHECK success|denied|failed
  metadata jsonb NOT NULL DEFAULT '{}'
  correlation_id text NOT NULL
  occurred_at timestamptz NOT NULL DEFAULT now()
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Indexes: (tenant_id, occurred_at DESC); (tenant_id, action, occurred_at DESC); (correlation_id)

idempotency_keys
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  scope text NOT NULL
  idempotency_key text NOT NULL
  request_hash text NOT NULL
  response_status integer NULL
  response_body jsonb NULL
  state text NOT NULL CHECK in_progress|completed|failed
  expires_at timestamptz NOT NULL
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(tenant_id, scope, idempotency_key)
Indexes: (tenant_id, expires_at)

outbox_events
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NULL FK tenants RESTRICT
  event_type text NOT NULL
  schema_version integer NOT NULL DEFAULT 1
  aggregate_type text NOT NULL
  aggregate_id text NOT NULL
  payload jsonb NOT NULL
  correlation_id text NOT NULL
  causation_id text NULL
  status text NOT NULL CHECK pending|published|failed
  attempts integer NOT NULL DEFAULT 0
  next_attempt_at timestamptz NOT NULL DEFAULT now()
  published_at timestamptz NULL
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Indexes: (status, next_attempt_at); (tenant_id, aggregate_type, aggregate_id)

webhook_endpoints
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  url text NOT NULL
  secret_ref text NOT NULL
  status text NOT NULL CHECK active|disabled
  event_types text[] NOT NULL
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Indexes: (tenant_id, status)

webhook_deliveries
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  webhook_endpoint_id uuid NOT NULL FK webhook_endpoints RESTRICT
  event_id uuid NOT NULL FK outbox_events RESTRICT
  status text NOT NULL CHECK pending|delivered|failed|dead_letter
  attempts integer NOT NULL DEFAULT 0
  last_status_code integer NULL
  next_attempt_at timestamptz NOT NULL DEFAULT now()
  delivered_at timestamptz NULL
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(webhook_endpoint_id, event_id)
Indexes: (tenant_id, status, next_attempt_at)
```

### 4.3 Row-Level Security

V1 uses application-enforced tenant filtering **plus PostgreSQL RLS as defense in depth** for tenant-owned tables where the connection model supports it safely. The request transaction sets a trusted tenant context from authenticated server state. No client-supplied tenant ID is trusted as authorization.

### 4.4 Migration Rules

- One migration per ticket unless the ticket explicitly defines an expand/migrate/contract sequence.
- Every migration has a tested rollback.
- Destructive changes use expand/migrate/contract and require premium review.
- Large index builds use concurrent strategies when supported and necessary.

## 5. API Architecture

### 5.1 Base Contract

- Base path: `/api/v1`.
- Resource names: plural, kebab-case.
- JSON request/response uses camelCase. Database remains snake_case.
- All list endpoints use `page`, `pageSize`, `sortBy`, `sortOrder`. Default `page=1`, `pageSize=25`, max `pageSize=100`. Unknown query fields return 400.
- Protected mutation endpoints that may be retried require `Idempotency-Key` when specified below.

Success envelope:

```json
{ "data": {}, "meta": {} }
```

List envelope:

```json
{
  "data": [],
  "meta": { "page": 1, "pageSize": 25, "total": 0, "totalPages": 0 }
}
```

Error envelope:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed.",
    "fields": { "fieldName": "Human-readable field error." }
  }
}
```

`fields` appears only for validation errors. Error codes are stable `SCREAMING_SNAKE_CASE`.

Standard statuses:

- `200` read/update/action success.
- `201` create success.
- `204` successful delete/archive with no body.
- `400` malformed or unsupported query/header.
- `401` unauthenticated.
- `403` authenticated but missing permission.
- `404` missing resource or resource existence must not be leaked.
- `409` conflict/duplicate/state conflict.
- `422` field validation.
- `429` rate limited.
- `500` unexpected safe generic response.
- `502/503/504` normalized dependency unavailable/bad gateway/timeout only where the endpoint contract explicitly exposes dependency status instead of creating a domain failure state.

### 5.2 Endpoint Inventory by MAS

**MAS-1 Tenant & Workforce Access**

```text
GET    /api/v1/me
GET    /api/v1/me/memberships
GET    /api/v1/organizations
POST   /api/v1/organizations
GET    /api/v1/organizations/{organizationId}
PATCH  /api/v1/organizations/{organizationId}
GET    /api/v1/organizations/{organizationId}/members
POST   /api/v1/organizations/{organizationId}/invitations
PATCH  /api/v1/organizations/{organizationId}/members/{membershipId}
DELETE /api/v1/organizations/{organizationId}/members/{membershipId}
GET    /api/v1/organizations/{organizationId}/roles
```

**MAS-2 AI Provider Gateway & BYOK**

```text
GET    /api/v1/providers
POST   /api/v1/providers
GET    /api/v1/providers/{providerConnectionId}
PATCH  /api/v1/providers/{providerConnectionId}
DELETE /api/v1/providers/{providerConnectionId}
POST   /api/v1/providers/{providerConnectionId}/test
GET    /api/v1/models
POST   /api/v1/models
PATCH  /api/v1/models/{modelConfigurationId}
DELETE /api/v1/models/{modelConfigurationId}
```

**MAS-3 Knowledge Source Lifecycle**

```text
GET    /api/v1/knowledge-sources
POST   /api/v1/knowledge-sources
GET    /api/v1/knowledge-sources/{sourceId}
PATCH  /api/v1/knowledge-sources/{sourceId}
POST   /api/v1/knowledge-sources/{sourceId}/sync
POST   /api/v1/knowledge-sources/{sourceId}/disable
GET    /api/v1/knowledge-documents
GET    /api/v1/knowledge-documents/{documentId}
```

**MAS-4 Retrieval & Grounding**

```text
POST   /api/v1/retrieval-queries
GET    /api/v1/retrieval-runs/{retrievalRunId}
```

**MAS-5 Customer Conversation Experience**

```text
POST   /api/v1/customer/conversations
GET    /api/v1/customer/conversations/{conversationId}
POST   /api/v1/customer/conversations/{conversationId}/messages
GET    /api/v1/customer/conversations/{conversationId}/events
POST   /api/v1/customer/conversations/{conversationId}/human-request
POST   /api/v1/customer/conversations/{conversationId}/feedback
```

**MAS-6 Agent Runtime & Routing / MAS-10 Agent Configuration**

```text
GET    /api/v1/agents
POST   /api/v1/agents
GET    /api/v1/agents/{agentId}
PATCH  /api/v1/agents/{agentId}
GET    /api/v1/agents/{agentId}/versions
POST   /api/v1/agents/{agentId}/versions
GET    /api/v1/agent-versions/{agentVersionId}
POST   /api/v1/agent-versions/{agentVersionId}/evaluate
POST   /api/v1/agent-versions/{agentVersionId}/publish
POST   /api/v1/agent-versions/{agentVersionId}/rollback
```

**MAS-7 Customer Context & Tool Execution**

```text
GET    /api/v1/tools
GET    /api/v1/tools/{toolId}
POST   /api/v1/tools/{toolId}/test
GET    /api/v1/tool-executions/{toolExecutionId}
```

Direct production tool mutation endpoints are internal. Customer mutations are initiated through conversation/action contracts so the model cannot bypass policy.

**MAS-8 Policy, Confirmation & Approval**

```text
GET    /api/v1/policies
POST   /api/v1/policies
GET    /api/v1/policies/{policyId}
POST   /api/v1/policies/{policyId}/versions
POST   /api/v1/customer/action-confirmations/{confirmationId}/confirm
POST   /api/v1/customer/action-confirmations/{confirmationId}/decline
GET    /api/v1/approvals
GET    /api/v1/approvals/{approvalId}
POST   /api/v1/approvals/{approvalId}/approve
POST   /api/v1/approvals/{approvalId}/reject
```

**MAS-9 Human Support & Escalation**

```text
GET    /api/v1/support-queues
GET    /api/v1/escalations
GET    /api/v1/escalations/{escalationId}
POST   /api/v1/escalations/{escalationId}/assign
POST   /api/v1/escalations/{escalationId}/reassign
POST   /api/v1/escalations/{escalationId}/resolve
POST   /api/v1/escalations/{escalationId}/reopen
POST   /api/v1/conversations/{conversationId}/messages
POST   /api/v1/conversations/{conversationId}/internal-notes
```

**MAS-11 Analytics & Audit**

```text
GET    /api/v1/analytics/overview
GET    /api/v1/analytics/providers
GET    /api/v1/analytics/tools
GET    /api/v1/analytics/retrieval
GET    /api/v1/audit-events
GET    /api/v1/audit-events/{auditEventId}
```

**MAS-12 Platform Operations**

```text
GET    /api/v1/platform/tenants
GET    /api/v1/platform/tenants/{tenantId}
GET    /api/v1/platform/health
GET    /api/v1/platform/providers
GET    /api/v1/platform/queues
GET    /api/v1/platform/jobs
GET    /api/v1/platform/dead-letters
GET    /api/v1/platform/feature-flags
PATCH  /api/v1/platform/feature-flags/{flagKey}
GET    /api/v1/platform/rate-limits
PATCH  /api/v1/platform/rate-limits/{limitKey}
GET    /api/v1/platform/usage
GET    /api/v1/platform/security-events
```

### 5.3 SSE Contract

`GET /api/v1/customer/conversations/{conversationId}/events` uses `text/event-stream` and emits only customer-safe event types:

```text
message.delta
message.completed
action.confirmation.required
action.approval.pending
escalation.created
human.joined
conversation.resolved
error.recoverable
```

SSE payload:

```json
{
  "eventId": "evt_...",
  "conversationId": "...",
  "type": "message.delta",
  "occurredAt": "ISO-8601",
  "data": {}
}
```

Internal chain-of-thought, raw prompts, secrets, policy internals, and unrestricted tool output are never sent through this stream.

## 6. Auth & Permissions

### 6.1 Workforce Authentication Flow

1. User opens a workforce application.
2. Unauthenticated request redirects to Keycloak OIDC Authorization Code + PKCE.
3. After callback, the server establishes a Serviq session. Access/refresh tokens remain server-side.
4. Browser receives an opaque/encrypted session cookie with `HttpOnly`, `SameSite=Lax`, `Secure` in production, and bounded expiry.
5. API request resolves session and OIDC identity server-side.
6. `users` and `memberships` map identity to tenant membership.
7. Tenant selection is taken from authenticated server state or an explicitly validated organization route, never trusted from an arbitrary header alone.
8. Permission guard resolves named capabilities from membership roles.
9. Repository/service queries include tenant ownership. Unauthorized resource existence may return 404 where the API contract requires non-disclosure.

### 6.2 Customer Identity Flow

- Anonymous session is allowed only for tenant-configured public support behavior.
- Protected customer data/actions require a tenant-signed short-lived assertion or configured identity integration.
- Customer assertion contains tenant, issuer, subject, expiration, and assurance level. Signature and audience are validated server-side.
- Customer identity is mapped to a tenant-scoped `customer_identities` record before protected tool access.

### 6.3 Permission Enforcement

- Navigation visibility is convenience only.
- Every protected API declares required capability.
- Object ownership is checked in database/service queries.
- Platform-operator permissions use a separate operator identity realm/claim and cannot be granted through tenant role APIs.
- Role/action matrix is the PRD Section 8 contract.

### 6.4 Premium Review Required

Authentication flows, permission middleware, customer identity assertions, platform-operator tenant access, session cookie behavior, and RLS policies require premium-model security review before merge.

## 7. Background Jobs

All jobs are durable, idempotent, observable, and bounded. Topic names below are contracts.

| Job | Trigger/topic | Retry policy | Idempotency key |
|---|---|---|---|
| Publish outbox | DB poll `outbox_events` | continuous, exponential on broker failure, never drop | `outbox_event.id` |
| Knowledge sync | `serviq.knowledge.sync.v1` | 3 retries at 30s, 5m, 30m, then DLQ | `tenantId:sourceId:syncVersion` |
| Document parse | `serviq.knowledge.parse.v1` | 3 retries at 30s, 5m, 30m, then DLQ | `documentId:documentVersion` |
| Chunk/embed/index | `serviq.knowledge.index.v1` | 3 retries at 1m, 10m, 30m, then DLQ | `documentId:documentVersion:embeddingProfile` |
| Analytics projection | `serviq.analytics.events.v1` | 5 retries with exponential backoff, then DLQ | source event ID |
| Webhook delivery | `serviq.webhooks.delivery.v1` | 8 retries with exponential backoff and jitter, capped at 24h, then dead-letter | `webhookEndpointId:eventId` |
| Notification | `serviq.notifications.v1` | 5 retries, then DLQ | notification command ID |
| Tool reconciliation | `serviq.tools.reconcile.v1` | 5 retries up to 30m, then human escalation | `toolExecutionId` |
| Approval expiry | scheduled scan every minute | safe repeat, no retry count needed | `approvalId:expiresAt` |
| Confirmation expiry | scheduled scan every minute | safe repeat, no retry count needed | `confirmationId:expiresAt` |
| Dead-letter replay | explicit platform-operator action | one replay command at a time, original idempotency preserved | original event/job ID + replay sequence |

Retry topics use `.retry` and `.dlq` suffixes. Consumers tolerate unknown additive payload fields and reject unsupported schema versions explicitly.

## 8. File Storage

### 8.1 Object Layout

Local bucket: `serviq-local-objects`. Cloud convention: `serviq-{environment}-objects`.

```text
tenants/{tenantId}/knowledge/{sourceId}/raw/{objectId}
tenants/{tenantId}/knowledge/{sourceId}/normalized/{documentId}/{version}
tenants/{tenantId}/exports/{exportId}
tenants/{tenantId}/evaluation/{evaluationRunId}
```

User-supplied filenames are metadata only and are never used as storage keys.

### 8.2 V1 Allowed Knowledge Uploads

| Type | Extensions | MIME allowlist | Max size |
|---|---|---|---:|
| PDF | `.pdf` | `application/pdf` | 25 MiB |
| Markdown | `.md`, `.markdown` | `text/markdown`, `text/plain` | 5 MiB |
| Plain text | `.txt` | `text/plain` | 5 MiB |

Both extension and MIME must pass. File signature/content sanity is checked before parsing. Files are treated as untrusted content and are never executed.

`Needs Product Decision: End-customer attachments are not architected or enabled until the PRD open question is resolved.`

## 9. Integrations

### 9.1 LLM Providers

**Purpose:** generation and, where configured, embedding/rerank models.  
**Access:** server-side BYOK secret reference.  
**Providers:** OpenAI, Anthropic, Gemini, OpenRouter.  
**Failure behavior:** explicit timeout, normalized provider error, circuit breaker, tenant-configured fallback if run budget permits, then deterministic/degraded response or escalation.  
**Rate behavior:** per-tenant and per-provider concurrency/token budgets. Provider `429` never creates an unbounded retry loop.

### 9.2 Keycloak OIDC

**Purpose:** workforce authentication in local/dev.  
**Auth:** OIDC Authorization Code + PKCE.  
**Failure behavior:** fail closed. Invalid/expired session returns 401. Identity provider outage does not bypass session validation.

### 9.3 Public Knowledge Fetcher

**Purpose:** retrieve approved public support pages/manifests.  
**Auth:** public HTTP only in V1 unless a future connector contract adds credentials.  
**Security:** HTTPS by default. Resolve DNS and reject loopback, link-local, private, metadata, and prohibited address ranges. Re-check redirects. Enforce response size/time limits, content-type allowlist, and tenant-configured domain allowlist.  
**Failure behavior:** source sync becomes `failed` with safe error code and retry control.  
**Crawl behavior:** obey access controls, configured request rate, and source ownership/terms. Never bypass authentication, robots/access restrictions, or anti-bot controls.

### 9.4 Synthetic Demo Operational Adapter

**Purpose:** provide realistic private customer/order/status/action data for the public-company demo without using real PII or proprietary systems.  
**Auth:** internal service capability only.  
**Failure behavior:** deterministic testable errors, timeout simulation, ambiguous-mutation simulation for reconciliation tests.  
**Contract:** exact tool set is frozen after the two demo-domain Product Decisions in PRD Section 16 are resolved.

### 9.5 Outbound Tenant Webhooks

**Purpose:** emit selected tenant events.  
**Auth:** HMAC signature using tenant endpoint secret.  
**Failure behavior:** acknowledge event creation synchronously, deliver asynchronously, duplicate-safe, bounded retry, dead-letter after exhaustion.  
**Security:** webhook signature implementation requires premium review.

## 10. Observability

### 10.1 Logging

Structured JSON fields:

```text
timestamp
level
service
requestId
traceId
spanId
tenantId (when safe)
userId/customerId (pseudonymous ID only when needed)
route/job/event
errorCode
message
```

Never log passwords, tokens, cookies, API keys, OTPs, full payment data, raw LLM prompts containing PII, or unrestricted tool output. Prompt/content capture is off by default and may only be enabled through a redacted evaluation/debug mode designed in a dedicated ticket.

### 10.2 Metrics

Minimum metrics:

- request count/rate, p50/p95/p99 latency, error rate;
- active SSE connections;
- DB pool saturation and query latency;
- cache hit/miss and rate-limit decisions;
- topic lag, consumer failures, dead-letter count;
- agent run duration, step count, model calls, tool calls;
- retrieval duration and result counts;
- provider latency, error, rate-limit, token/usage estimates;
- tool outcome and ambiguous-state count;
- escalation, containment/resolution, feedback;
- knowledge sync/index backlog.

Tenant labels on high-volume metrics must use cardinality controls. Per-tenant detailed analytics belong in the event/data layer, not unbounded metrics labels.

### 10.3 Tracing

One distributed trace covers ingress -> auth/tenant resolution -> conversation persistence -> agent -> retrieval/provider/policy/tool -> response -> durable event publication. Secrets and raw sensitive content are excluded from spans.

### 10.4 Health Endpoints

```text
GET /health/live   -> process liveness only
GET /health/ready  -> required dependency readiness for that process
GET /health/info   -> build/version metadata, protected or internal-only in production
```

Readiness never performs expensive provider calls.

## 11. Deployment Assumptions

### 11.1 Environments

- `local`: Docker Compose, deterministic mocks available, no paid dependency required.
- `test`: ephemeral CI dependencies and fake external providers.
- `staging`: production-like configuration with synthetic data.
- `production`: cloud deployment after infrastructure ADRs and load/security gates.

### 11.2 Required Configuration Names

Exact secrets are not committed. Initial environment/config contract:

```text
SERVIQ_ENV
SERVIQ_PUBLIC_BASE_URL
SERVIQ_API_BASE_URL
DATABASE_URL
VALKEY_URL
KAFKA_BOOTSTRAP_SERVERS
OBJECT_STORAGE_ENDPOINT
OBJECT_STORAGE_BUCKET
OBJECT_STORAGE_ACCESS_KEY
OBJECT_STORAGE_SECRET_KEY
OIDC_ISSUER_URL
OIDC_CLIENT_ID
OIDC_CLIENT_SECRET
OIDC_REDIRECT_URI
SESSION_SECRET
LLM_GATEWAY_URL
LLM_GATEWAY_INTERNAL_TOKEN
OTEL_EXPORTER_OTLP_ENDPOINT
LOG_LEVEL
```

Provider BYOK keys are tenant secrets stored through the secret adapter, not static environment variables per tenant.

### 11.3 Local Startup

The root repository must expose documented commands equivalent to:

```text
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

Docker Compose profiles allow minimal core startup and optional broker/observability profiles. CI runs a deterministic fake LLM so tests do not require paid calls.

### 11.4 CI Expectations

Pull requests run formatting, lint, type checks, unit, integration, API, tenant-isolation, migration up/down, contract tests, dependency scan, secret scan, SAST, container validation where applicable, E2E smoke tests for affected surfaces, and docs/link checks.

## 12. System Boundaries & Contracts

The contracts below are architect-owned. Tickets may add validation detail without changing field names/meaning. Any change to these contracts requires contract-change control.

### CONTRACT C-1 [MAS-1 Tenant/Auth Context -> all tenant MASs]

**Direction:** request guard supplies trusted context to services.  
**In-memory type:**

```json
{
  "requestId": "string",
  "tenantId": "uuid",
  "actor": {
    "type": "tenant_user|customer|service|platform_operator",
    "id": "string"
  },
  "userId": "uuid|null",
  "customerId": "uuid|null",
  "permissions": ["string"],
  "assuranceLevel": "anonymous|verified|workforce|platform"
}
```

**Errors:** missing identity 401, missing tenant permission 403, inaccessible object 404 where non-disclosure applies.  
**Owner:** MAS-1.

### CONTRACT C-2 [MAS-5 Conversation -> MAS-6 Agent Runtime]

**Direction:** persisted customer message requests an agent run through outbox/event.  
**Event:** `agent.run.requested` on `serviq.agent.runs.v1`.

```json
{
  "eventId": "uuid",
  "schemaVersion": 1,
  "tenantId": "uuid",
  "conversationId": "uuid",
  "triggerMessageId": "uuid",
  "agentVersionId": "uuid",
  "correlationId": "string",
  "occurredAt": "iso8601"
}
```

**Error behavior:** duplicate event is ignored by `eventId`/run uniqueness. Missing/retired agent version moves event to failed/DLQ and conversation receives recoverable error or escalation according to deployment policy.  
**Owner:** MAS-5 for event creation, MAS-6 for consumption behavior.

### CONTRACT C-3 [MAS-6 Agent Runtime <-> MAS-4 Retrieval]

**Direction:** synchronous internal service call.

Request:

```json
{
  "tenantId": "uuid",
  "query": "string 1..4000",
  "accessScope": "customer|internal",
  "topK": "integer 1..20",
  "sourceIds": ["uuid"],
  "knowledgeVersion": "integer|null"
}
```

Response:

```json
{
  "results": [
    {
      "chunkId": "uuid",
      "documentId": "uuid",
      "sourceId": "uuid",
      "content": "string",
      "score": "number",
      "citation": { "title": "string", "uri": "string|null", "location": "string|null" }
    }
  ],
  "retrievalRunId": "uuid"
}
```

**Errors:** typed `RETRIEVAL_UNAVAILABLE`, `INVALID_RETRIEVAL_QUERY`. No fallback to another tenant or disabled source.  
**Owner:** MAS-4.

### CONTRACT C-4 [MAS-6 Agent Runtime <-> MAS-2 LLM Gateway]

Request:

```json
{
  "tenantId": "uuid",
  "modelAlias": "string",
  "purpose": "classification|generation|evaluation",
  "messages": [{ "role": "system|user|assistant", "content": "string" }],
  "responseSchema": {},
  "maxOutputTokens": "integer",
  "timeoutMs": "integer",
  "stream": "boolean",
  "correlationId": "string"
}
```

Non-stream response:

```json
{
  "content": "string|null",
  "structured": {},
  "provider": "openai|anthropic|gemini|openrouter",
  "upstreamModel": "string",
  "usage": { "inputTokens": "integer|null", "outputTokens": "integer|null" },
  "finishReason": "string",
  "requestId": "string|null"
}
```

**Errors:** normalized `PROVIDER_RATE_LIMITED`, `PROVIDER_TIMEOUT`, `PROVIDER_UNAVAILABLE`, `PROVIDER_INVALID_REQUEST`, `PROVIDER_AUTH_FAILED`. The gateway never returns a raw provider key or raw provider exception to callers.  
**Owner:** MAS-2.

### CONTRACT C-5 [MAS-6 Agent Runtime -> MAS-7 Tool Proposal]

```json
{
  "tenantId": "uuid",
  "agentRunId": "uuid",
  "toolKey": "string",
  "toolVersion": "integer",
  "arguments": {},
  "customerId": "uuid|null",
  "correlationId": "string"
}
```

Tool arguments are validated against the frozen JSON Schema in `tool_versions.input_schema`. Unknown fields are rejected. Invalid model output becomes `TOOL_ARGUMENT_VALIDATION_FAILED` and cannot execute.  
**Owner:** MAS-7.

### CONTRACT C-6 [MAS-7 Tool -> MAS-8 Policy Decision]

Request:

```json
{
  "tenantId": "uuid",
  "toolExecutionId": "uuid",
  "toolKey": "string",
  "toolRiskClass": "read_only|low|medium|high",
  "customerId": "uuid|null",
  "customerAssuranceLevel": "anonymous|verified",
  "arguments": {},
  "context": {}
}
```

Response:

```json
{
  "decision": "allow|deny|require_confirmation|require_human_approval",
  "policyVersionId": "uuid",
  "reasonCode": "string",
  "confirmationExpiresAt": "iso8601|null",
  "approvalExpiresAt": "iso8601|null"
}
```

**Rule:** missing policy for mutation returns `deny`, never implicit allow.  
**Owner:** MAS-8.

### CONTRACT C-7 [MAS-8 Approval -> MAS-9 Human Support]

**Event:** `approval.requested` on `serviq.support.approvals.v1`.

```json
{
  "eventId": "uuid",
  "tenantId": "uuid",
  "approvalId": "uuid",
  "conversationId": "uuid",
  "toolExecutionId": "uuid",
  "riskClass": "low|medium|high",
  "reasonCode": "string",
  "expiresAt": "iso8601",
  "correlationId": "string"
}
```

MAS-9 may assign/display the approval. Only MAS-8 changes approval decision state.  
**Owner:** MAS-8.

### CONTRACT C-8 [MAS-6 Agent Runtime -> MAS-9 Escalation]

Request/service command:

```json
{
  "tenantId": "uuid",
  "conversationId": "uuid",
  "agentRunId": "uuid|null",
  "reasonCode": "customer_requested|low_evidence|policy_required|tool_failed|auth_required|budget_exhausted|system_failure",
  "priority": "low|normal|high|urgent",
  "evidenceChunkIds": ["uuid"],
  "toolExecutionIds": ["uuid"],
  "recommendedNextAction": "string"
}
```

Response:

```json
{ "escalationId": "uuid", "queueId": "uuid", "status": "open|assigned" }
```

Creating the escalation updates conversation ownership/state in the same domain transaction/outbox sequence.  
**Owner:** MAS-9.

### CONTRACT C-9 [MAS-3 Knowledge Lifecycle -> MAS-4 Retrieval Index]

**Event:** `knowledge.document.indexed` on `serviq.knowledge.events.v1`.

```json
{
  "eventId": "uuid",
  "tenantId": "uuid",
  "sourceId": "uuid",
  "documentId": "uuid",
  "documentVersion": "integer",
  "contentHash": "string",
  "chunkCount": "integer",
  "embeddingModelAlias": "string|null",
  "correlationId": "string"
}
```

Retrieval may serve only document versions whose source/document state is active/ready according to the transactionally stored source of truth.  
**Owner:** MAS-3.

### CONTRACT C-10 [All MASs -> MAS-11 Audit]

**Event:** `audit.event.recorded` on `serviq.audit.events.v1`.

```json
{
  "eventId": "uuid",
  "schemaVersion": 1,
  "tenantId": "uuid|null",
  "actor": { "type": "customer|tenant_user|service|platform_operator", "id": "string" },
  "action": "string",
  "resource": { "type": "string", "id": "string" },
  "outcome": "success|denied|failed",
  "metadata": {},
  "correlationId": "string",
  "occurredAt": "iso8601"
}
```

`metadata` must be explicitly allow-listed by event producer and must not contain secret values.  
**Owner:** MAS-11 owns persistence/query. Producer owns accurate action/resource/outcome.

### CONTRACT C-11 [All MASs -> MAS-11 Usage/Analytics]

**Event:** `usage.recorded` on `serviq.analytics.events.v1`.

```json
{
  "eventId": "uuid",
  "tenantId": "uuid",
  "eventType": "string",
  "quantity": "integer",
  "amountMicrousd": "integer|null",
  "dimensions": {},
  "occurredAt": "iso8601"
}
```

Analytics failures never block the customer response path. Durable source domain state remains authoritative.  
**Owner:** MAS-11.

### CONTRACT C-12 [Customer SSE <- MAS-5/MAS-9]

Only the public event types in Section 5.3 may reach customers. Every event is filtered through customer visibility rules before serialization. Internal notes, evidence scores, raw policy rules, provider metadata, and tool internals are prohibited.  
**Owner:** MAS-5.

## 13. Parallelization Map

### Phase 0 — Repository Foundation

**Blocking:** scaffold monorepo, Docker Compose, base CI, shared API/error contracts, database/migration harness, auth skeleton, `docs/repo_context.md`.  
**Owner:** MAS-13.  
No implementation ticket may invent file paths before the repo audit is created.

### Phase 1 — Parallel Foundations

Can run in parallel after Phase 0 contracts:

- MAS-1 Tenant & Workforce Access.
- MAS-2 Provider Gateway/BYOK using mocked tenant context until MAS-1 integration.
- MAS-3 Knowledge Source Lifecycle.
- MAS-5 Customer Conversation persistence/stream shell.
- MAS-11 Audit event persistence/projector.

### Phase 2 — Intelligence and Governance

- MAS-4 depends on MAS-3 schema/contracts.
- MAS-6 depends on MAS-2, MAS-4, and MAS-5 contracts, but can start against mocks.
- MAS-7 depends on MAS-1 and the selected demo-domain Product Decision.
- MAS-8 depends on MAS-7 tool schemas and MAS-1 authorization.

### Phase 3 — Human and Management Surfaces

- MAS-9 depends on MAS-5, MAS-6, MAS-8.
- MAS-10 can build frontend slices in parallel against frozen API mocks, then integrate as each MAS endpoint becomes available.
- MAS-11 analytics projections expand as source events stabilize.

### Phase 4 — Platform Operations and Hardening

- MAS-12 consumes health/audit/queue/provider contracts.
- MAS-13 runs security, E2E, failure, migration, contract drift, and load gates across all integrated MASs.

### Integration Order

```text
MAS-13 scaffold
  -> MAS-1 tenant/auth contract
  -> MAS-2 + MAS-3 + MAS-5 + MAS-11 foundations
  -> MAS-4 retrieval
  -> MAS-6 agent
  -> MAS-7 tools
  -> MAS-8 policy/approval
  -> MAS-9 support
  -> MAS-10 full client integration
  -> MAS-12 platform operations
  -> MAS-13 release hardening/load evidence
```

## 14. Risk Register

| Area | Risk | Required handling |
|---|---|---|
| Workforce authentication/session | Credential/session flaws expose tenants | **Premium review required.** Use OIDC standard flow, no localStorage tokens, explicit route guards, auth failure tests. |
| Tenant authorization/RLS | Cross-tenant leakage is a critical breach | **Premium review required.** Tenant-scoped queries, RLS defense in depth, adversarial permission tests. |
| Customer identity assertions | Forged customer identity exposes private records | **Premium review required.** Signed short-lived assertions, audience/issuer/expiry checks, assurance-level policy. |
| BYOK secret storage | Provider keys can create billing/security exposure | **Premium review required.** Secret adapter, encryption-at-rest design, one-time/masked display, redacted logs. |
| Public web ingestion | SSRF, malware, prompt injection, copyright/terms risk | **Premium review required.** Network address checks, redirect re-checks, domain controls, content limits, untrusted-content boundary, legal/source manifest policy. |
| LLM prompts with user/retrieved data | Prompt injection or PII leakage | **Premium review required.** Separate instructions/data, minimize context, validate structured output, redact logs. |
| Tool mutations | Duplicate or unauthorized customer-impacting actions | **Premium review required.** Typed tools, policy before execution, idempotency, reconciliation, human approval for configured risk. |
| Webhook signatures | Signature bug enables forged callbacks or leaks | **Premium review required.** Standard HMAC construction, replay window, constant-time compare, exact signing contract. |
| Database migrations | Live lock/data loss/schema drift | **Premium review required** for destructive or large-table changes. Expand/migrate/contract, tested rollback. |
| Kafka/event concurrency | Duplicate/out-of-order processing | Idempotent consumers, aggregate partition keys, outbox, sequence/version checks where order matters. |
| Semantic/vector retrieval | Index dimension/model drift | Freeze V1 embedding profile in an ADR before vector index creation. Store model alias with chunks. Reindex through versioned job. |
| Observability cardinality/PII | Metrics cost/exposure and sensitive logs | Limit labels, pseudonymous IDs, default redaction, no raw prompts/secrets. |
| 10M concurrency objective | Premature distributed complexity and false claims | Keep stateless contracts and scale seams, but introduce sharding/multi-region only from measured bottlenecks. Publish measured load evidence separately. |
| Local developer resource use | Full stack too heavy for contributors | Compose profiles and deterministic mocks. Broker/observability profiles are optional until a ticket requires them. |

### Architecture Decisions Still Blocked by Product Decisions

- `Needs Product Decision: Select the first real public-company support corpus before freezing demo tool schemas and knowledge-source fixtures.`
- `Needs Product Decision: Select the matching synthetic operational domain/tool set before MAS-7 tickets are written.`
- `Needs Product Decision: Resolve end-customer attachment scope before any customer upload endpoint, storage path, validation rule, or UI is created.`

These blocked areas must not be guessed by a builder.
