# Architecture Plan: Serviq — Production V1

**Status:** Architecture baseline v1.3  
**Scope:** Production V1 defined by `docs/PRD.md`  
**Contract change records:** `docs/contract-changes/CCR-001-foundation-hardening.md` and `docs/contract-changes/CCR-003-doordash-stripe-demo-composition.md`  
**Architecture rule:** Builders implement frozen contracts. Any API, database, event, shared-type, config, file-path, auth, or permission contract change requires architect-owned contract change control before implementation.  
**Scale statement:** Serviq preserves a path toward millions of concurrent users and a long-term 10M concurrent-connection target. Neither 10M concurrency nor 10M RPS is a verified claim until reproducible load tests prove it.

## 1. Stack Decisions

| Layer | Choice | Reason |
|---|---|---|
| Frontend | Next.js 16.2.x + React 19.2 + TypeScript strict | Production React stack with SSR, routing, streaming, and mature tooling. |
| Forms | react-hook-form + Zod | Explicit form state and shared validation vocabulary. |
| Server state | TanStack Query where interactive client fetching is required | Predictable caching, retries, and invalidation. |
| Styling | Tailwind CSS + Serviq-owned accessible primitives | Fast implementation without locking product UX to a vendor. |
| Backend | Python 3.14.x + FastAPI 0.140.x + Pydantic 2.x | Strong async/API and AI ecosystem. |
| ORM/migrations | SQLAlchemy 2.x + Alembic | Explicit relational access and migration discipline. |
| Database | PostgreSQL 18.x | Transactional source of truth, RLS, FTS, UUIDv7. |
| Vector search | pgvector | Zero-cost V1 retrieval infrastructure behind an abstraction. |
| Cache | Valkey 8.x compatible | Rebuildable cache, rate limits, short-lived coordination. |
| Broker | Kafka-compatible contract; Redpanda local; MSK-compatible scale path | Durable asynchronous workloads and partitioning. |
| Object storage | MinIO/S3-compatible local; S3 production mapping | Cloud-portable object semantics. |
| Workforce auth | Keycloak 26.7.x OIDC locally; OIDC abstraction in product | Standards-based, zero-cost local identity. |
| LLM gateway | Serviq-owned provider-neutral contract; LiteLLM-compatible adapter permitted | BYOK across OpenAI, Anthropic, Gemini, OpenRouter. |
| Observability | OpenTelemetry + Prometheus + Grafana + Loki + Tempo | Full local traces, metrics, logs without paid SaaS. |
| Local orchestration | Docker Compose profiles | Reproducible zero-dollar development. |
| Production scale target | OCI containers, Kubernetes after measured need | Horizontal scale without making Kubernetes mandatory for local V1. |
| IaC | Terraform when AWS deployment begins | Reviewable infrastructure changes. |
| CI/CD | GitHub Actions | Native repository automation. |
| Load testing | k6 | Reproducible throughput and concurrency tests. |

Exact patch versions are locked by repository lockfiles after scaffolding and recorded in `docs/repo_context.md`.

## 2. Frontend Architecture

### 2.1 Applications

```text
apps/
  client-console/
  customer-web/
  platform-console/
packages/
  ui/
  contracts/
  config/
  observability/
  security/
  testkit/
```

- `client-console` contains onboarding, tenant configuration, analytics, conversations, and the Human Support Workspace.
- `customer-web` is the standalone customer support reference surface and future widget reference implementation.
- `platform-console` is a separate Serviq operator trust surface.

### 2.2 Routing

Client routes:

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

### 2.3 Frontend Module Contract

Every feature uses:

```text
src/features/[feature]/
  components/
  hooks/
  api.ts
  types.ts
  schemas.ts
```

Cross-feature imports are prohibited. Shared API/domain contracts belong in `packages/contracts`; shared visual primitives belong in `packages/ui`. Components do not invent API shapes.

### 2.4 State, Forms, and Fetching

- Server components/route handlers are preferred when they improve security or initial loading.
- TanStack Query owns interactive server state.
- Local UI state stays local. No V1 global store without an ADR.
- Forms use react-hook-form + Zod and server validation remains authoritative.
- Client API calls go through feature `api.ts` plus the shared authenticated client. Inline ad hoc `fetch` in feature components is prohibited.

### 2.5 Mandatory UI States

Every data-driven screen implements loading, empty, error, permission-denied when applicable, success, mutation-pending, mutation-success, and mutation-failure states. No horizontal page scroll at 375 px. All interactive controls are keyboard operable and properly labeled.

## 3. Backend Architecture

### 3.1 Deployment Shape

Production V1 starts as a **modular monolith plus durable workers**. Logical boundaries are extraction contracts, not a mandate to deploy fifteen microservices on day one.

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
        rate_limits.py
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
        privacy/
        platform_ops/
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

Each domain module follows:

```text
router.py -> service.py -> repository.py -> database
schemas.py
models.py
permissions.py
errors.py
```

Routers validate transport input. Services own business rules and transactions. Repositories own persistence queries. Modules call exported service interfaces, never another module's repository.

### 3.2 Validation and Errors

- Unknown request body fields are rejected.
- Path/query/header/body/upload/model-structured-output values are validated server-side.
- One global exception layer converts typed domain errors to the Section 5 error envelope.
- Unexpected exceptions return `INTERNAL_ERROR` without stack traces, secrets, prompts, or provider internals.
- No external HTTP, model, broker, or tool call runs inside a database transaction.

### 3.3 Agent Runtime State Machine

```text
RECEIVE
-> AUTH_CONTEXT
-> REQUEST_CLASSIFICATION
-> FAST_PATH_CHECK
-> CONTEXT_PLANNING
-> RETRIEVAL / TOOL_PROPOSAL / MODEL_REASONING
-> POLICY_CHECK
-> CONFIRMATION_OR_APPROVAL (when required)
-> TOOL_EXECUTION (when required)
-> RESULT_VERIFICATION
-> RESPONSE_GENERATION
-> OUTPUT_GUARDRAIL
-> RESPOND
-> COMPLETE

Any state may transition to ESCALATE or FAIL_SAFE.
```

### 3.4 Frozen Default Agent Budgets

These are Production V1 defaults. Tenant agent versions may configure stricter values. Raising a ceiling above these defaults requires an authorized AI Manager and must remain within platform hard limits.

| Budget | V1 default | Platform hard limit |
|---|---:|---:|
| Maximum agent steps | 12 | 20 |
| Maximum model calls per run | 4 | 8 |
| Maximum retrieval calls per run | 3 | 6 |
| Maximum tool calls per run | 4 | 8 |
| Maximum mutating tool executions per run | 1 | 2, each independently policy-authorized |
| Interactive wall-clock budget | 45 s | 90 s |
| Model request timeout | 20 s | 30 s |
| Read-only tool timeout | 10 s | 20 s |
| Mutating tool timeout | 20 s | 30 s |
| Maximum aggregate model input | 32,000 tokens | 64,000 tokens |
| Maximum model output per call | 1,500 tokens | 4,000 tokens |
| Maximum normalized tool output passed to model | 20,000 UTF-8 characters/tool | 40,000 aggregate/run |

Retry rules:

- one automatic retry is allowed for a clearly transient, non-billable-before-completion model transport failure if time budget permits; otherwise route to configured fallback;
- provider `429` does not loop. Use fallback only when configured and within budget;
- read-only tools may retry once when the adapter declares the operation retry-safe;
- a mutating tool is never blindly retried when its external outcome is unknown. It enters reconciliation;
- budget exhaustion transitions to deterministic fallback or escalation.

## 4. Database Architecture

### 4.1 Conventions

- PostgreSQL 18.x; snake_case database identifiers.
- Primary keys: `uuid DEFAULT uuidv7()`.
- Mutable tables include `created_at timestamptz NOT NULL DEFAULT now()` and `updated_at timestamptz NOT NULL DEFAULT now()`.
- Tenant-owned tables include `tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT` and an index beginning with `tenant_id`.
- Money is integer minor units plus ISO currency.
- Status/type fields use `text` + CHECK constraints in V1.
- Foreign keys are indexed.
- Multi-table state transitions are transactional and publish through the transactional outbox.

### 4.2 V1 Tables

The following is the frozen schema contract. Migrations may split table creation across tickets but may not rename, repurpose, or silently add cross-MAS fields without contract change control.

**Migration sequencing note (CCR-004):** the final `memberships.created_by_invitation_id -> organization_invitations(id) ON DELETE SET NULL` contract remains frozen, but the OPE-277 migration creates the nullable column before the invitation table exists. OPE-278 creates `organization_invitations` and then adds that foreign-key constraint in the same revision. This is a migration-order clarification only; the final schema contract below is unchanged.

```text
tenants
  id uuid PK
  slug text NOT NULL UNIQUE CHECK length 3..63
  display_name text NOT NULL CHECK length 1..120
  status text NOT NULL CHECK active|suspended|deleted
  default_locale text NOT NULL DEFAULT 'en'
Indexes: UNIQUE(slug), (status)

users
  id uuid PK
  oidc_issuer text NOT NULL
  oidc_subject text NOT NULL
  email text NOT NULL
  display_name text NOT NULL
  status text NOT NULL CHECK active|disabled
Constraints: UNIQUE(oidc_issuer, oidc_subject)
Indexes: (email)

memberships
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  user_id uuid NOT NULL FK users RESTRICT
  status text NOT NULL CHECK active|suspended
  created_by_invitation_id uuid NULL FK organization_invitations SET NULL
Constraints: UNIQUE(tenant_id, user_id)
Indexes: (tenant_id, status), (user_id)

roles
  id uuid PK
  tenant_id uuid NULL FK tenants RESTRICT
  key text NOT NULL CHECK length 2..64
  display_name text NOT NULL CHECK length 1..80
  is_system boolean NOT NULL DEFAULT false
Constraints: UNIQUE NULLS NOT DISTINCT(tenant_id, key)
Indexes: (tenant_id)

role_permissions
  id uuid PK
  role_id uuid NOT NULL FK roles CASCADE
  permission_key text NOT NULL CHECK length 2..120
Constraints: UNIQUE(role_id, permission_key)
Indexes: (role_id)

membership_roles
  id uuid PK
  membership_id uuid NOT NULL FK memberships CASCADE
  role_id uuid NOT NULL FK roles RESTRICT
Constraints: UNIQUE(membership_id, role_id)
Indexes: (membership_id), (role_id)

organization_invitations
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  email_normalized text NOT NULL CHECK length 3..320
  token_hash text NOT NULL UNIQUE
  status text NOT NULL CHECK pending|accepted|revoked|expired
  invited_by_user_id uuid NOT NULL FK users RESTRICT
  accepted_by_user_id uuid NULL FK users RESTRICT
  expires_at timestamptz NOT NULL
  accepted_at timestamptz NULL
  revoked_at timestamptz NULL
Constraints: token plaintext is never persisted
Indexes: (tenant_id, status, expires_at), (tenant_id, email_normalized)
Partial unique index: UNIQUE(tenant_id, email_normalized) WHERE status='pending'

organization_invitation_roles
  id uuid PK
  invitation_id uuid NOT NULL FK organization_invitations CASCADE
  role_id uuid NOT NULL FK roles RESTRICT
Constraints: UNIQUE(invitation_id, role_id)
Indexes: (invitation_id), (role_id)

provider_connections
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  provider text NOT NULL CHECK openai|anthropic|gemini|openrouter
  display_name text NOT NULL CHECK length 1..80
  secret_ref text NOT NULL
  status text NOT NULL CHECK untested|active|invalid|disabled
  last_tested_at timestamptz NULL
  last_error_code text NULL
  created_by uuid NOT NULL FK users RESTRICT
Constraints: UNIQUE(tenant_id, display_name)
Indexes: (tenant_id, provider, status)

model_configurations
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  provider_connection_id uuid NOT NULL FK provider_connections RESTRICT
  alias text NOT NULL CHECK length 1..80
  upstream_model text NOT NULL CHECK length 1..160
  purpose text NOT NULL CHECK generation|embedding|rerank
  enabled boolean NOT NULL DEFAULT true
Constraints: UNIQUE(tenant_id, alias)
Indexes: (tenant_id, purpose, enabled), (provider_connection_id)

agents
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  name text NOT NULL CHECK length 1..100
  status text NOT NULL CHECK active|archived
  created_by uuid NOT NULL FK users RESTRICT
Constraints: UNIQUE(tenant_id, name)
Indexes: (tenant_id, status)

agent_versions
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  agent_id uuid NOT NULL FK agents RESTRICT
  version integer NOT NULL CHECK version > 0
  status text NOT NULL CHECK draft|published|retired
  config jsonb NOT NULL
  config_schema_version integer NOT NULL DEFAULT 1
  published_by uuid NULL FK users RESTRICT
  published_at timestamptz NULL
Constraints: UNIQUE(agent_id, version)
Indexes: (tenant_id, agent_id, status)

agent_deployments
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  agent_id uuid NOT NULL FK agents RESTRICT
  agent_version_id uuid NOT NULL FK agent_versions RESTRICT
  channel text NOT NULL CHECK customer_web
  status text NOT NULL CHECK active|paused
Constraints: UNIQUE(tenant_id, channel)
Indexes: (tenant_id, status), (agent_version_id)

knowledge_sources
  id uuid PK
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
Constraints: URL/sitemap requires source_uri; file types require object_key
Indexes: (tenant_id, status), (tenant_id, source_type)

knowledge_upload_cleanups
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  source_id uuid NOT NULL
  object_id uuid NOT NULL
  object_key text NOT NULL
  status text NOT NULL CHECK prepared|pending|referenced|succeeded|exhausted
  attempt_count integer NOT NULL DEFAULT 0 CHECK 0..3
  next_attempt_at timestamptz NULL
  last_error_code text NULL
  resolved_at timestamptz NULL
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(tenant_id, source_id), UNIQUE(object_key); unresolved states require next_attempt_at and no resolved_at; terminal states require resolved_at and no next_attempt_at
Indexes: (tenant_id, status, next_attempt_at), (status, next_attempt_at)

knowledge_documents
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  source_id uuid NOT NULL FK knowledge_sources RESTRICT
  canonical_uri text NULL
  title text NOT NULL DEFAULT ''
  content_hash text NOT NULL
  document_version integer NOT NULL
  status text NOT NULL CHECK active|deprecated|failed
  fetched_at timestamptz NULL
Constraints: UNIQUE(source_id, canonical_uri, document_version)
Indexes: (tenant_id, source_id, status), (content_hash)

knowledge_chunks
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  document_id uuid NOT NULL FK knowledge_documents CASCADE
  ordinal integer NOT NULL CHECK ordinal >= 0
  content text NOT NULL
  token_count integer NOT NULL CHECK token_count >= 0
  metadata jsonb NOT NULL DEFAULT '{}'
  embedding vector NULL
  embedding_model_alias text NULL
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
Constraints: UNIQUE(document_id, ordinal)
Indexes: (tenant_id, document_id), GIN(tsv); vector index only after embedding profile ADR

customers
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  external_ref text NULL
  display_name text NULL CHECK length <= 120
  email text NULL
  status text NOT NULL CHECK active|blocked|deleted
  metadata jsonb NOT NULL DEFAULT '{}'
  deleted_at timestamptz NULL
Indexes: (tenant_id, email), (tenant_id, status)
Partial unique index: UNIQUE(tenant_id, external_ref) WHERE external_ref IS NOT NULL

customer_identities
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  customer_id uuid NOT NULL FK customers CASCADE
  issuer text NOT NULL
  subject text NOT NULL
  assurance_level text NOT NULL CHECK anonymous|verified
Constraints: UNIQUE(tenant_id, issuer, subject)
Indexes: (tenant_id, customer_id)

conversations
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  customer_id uuid NULL FK customers RESTRICT
  agent_deployment_id uuid NOT NULL FK agent_deployments RESTRICT
  status text NOT NULL CHECK open|pending|escalated|resolved|reopened
  channel text NOT NULL CHECK customer_web
  current_owner_type text NOT NULL CHECK ai|human
  last_message_at timestamptz NOT NULL DEFAULT now()
  resolved_at timestamptz NULL
Indexes: (tenant_id, status, last_message_at DESC), (tenant_id, customer_id, last_message_at DESC)

messages
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  conversation_id uuid NOT NULL FK conversations CASCADE
  sequence bigint NOT NULL CHECK sequence > 0
  actor_type text NOT NULL CHECK customer|ai|tenant_user|system
  actor_id uuid NULL
  visibility text NOT NULL CHECK customer|internal
  content_type text NOT NULL CHECK text|status|action_card
  content text NOT NULL DEFAULT ''
  metadata jsonb NOT NULL DEFAULT '{}'
Constraints: UNIQUE(conversation_id, sequence)
Indexes: (tenant_id, conversation_id, sequence)

agent_runs
  id uuid PK
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
Indexes: (tenant_id, conversation_id, created_at DESC), (tenant_id, status, created_at)

agent_steps
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  agent_run_id uuid NOT NULL FK agent_runs CASCADE
  ordinal integer NOT NULL CHECK ordinal >= 0
  step_type text NOT NULL
  status text NOT NULL CHECK started|completed|failed|skipped
  input_summary jsonb NOT NULL DEFAULT '{}'
  output_summary jsonb NOT NULL DEFAULT '{}'
  started_at timestamptz NOT NULL DEFAULT now()
  completed_at timestamptz NULL
Constraints: UNIQUE(agent_run_id, ordinal)
Indexes: (tenant_id, agent_run_id, ordinal)

retrieval_runs
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  agent_run_id uuid NULL FK agent_runs CASCADE
  query_text text NOT NULL
  top_k integer NOT NULL CHECK top_k BETWEEN 1 AND 50
  status text NOT NULL CHECK completed|failed
  duration_ms integer NOT NULL CHECK duration_ms >= 0
Indexes: (tenant_id, agent_run_id, created_at)

retrieval_results
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  retrieval_run_id uuid NOT NULL FK retrieval_runs CASCADE
  chunk_id uuid NOT NULL FK knowledge_chunks RESTRICT
  rank integer NOT NULL CHECK rank > 0
  lexical_score double precision NULL
  vector_score double precision NULL
  final_score double precision NOT NULL
Constraints: UNIQUE(retrieval_run_id, rank), UNIQUE(retrieval_run_id, chunk_id)
Indexes: (tenant_id, retrieval_run_id, rank)

tools
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  key text NOT NULL CHECK length 2..120
  display_name text NOT NULL CHECK length 1..120
  status text NOT NULL CHECK active|disabled
  risk_class text NOT NULL CHECK read_only|low|medium|high
Constraints: UNIQUE(tenant_id, key)
Indexes: (tenant_id, status)

tool_versions
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  tool_id uuid NOT NULL FK tools RESTRICT
  version integer NOT NULL CHECK version > 0
  input_schema jsonb NOT NULL
  output_schema jsonb NOT NULL
  implementation_key text NOT NULL
Constraints: UNIQUE(tool_id, version)
Indexes: (tenant_id, tool_id, version DESC)

policies
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  key text NOT NULL CHECK length 2..120
  display_name text NOT NULL CHECK length 1..120
  status text NOT NULL CHECK active|disabled
Constraints: UNIQUE(tenant_id, key)
Indexes: (tenant_id, status)

policy_versions
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  policy_id uuid NOT NULL FK policies RESTRICT
  version integer NOT NULL CHECK version > 0
  rules jsonb NOT NULL
  created_by uuid NOT NULL FK users RESTRICT
Constraints: UNIQUE(policy_id, version)
Indexes: (tenant_id, policy_id, version DESC)

tool_executions
  id uuid PK
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
Constraints: UNIQUE(tenant_id, idempotency_key)
Indexes: (tenant_id, agent_run_id, created_at), (tenant_id, status, created_at)

action_confirmations
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  tool_execution_id uuid NOT NULL FK tool_executions RESTRICT
  customer_id uuid NULL FK customers RESTRICT
  status text NOT NULL CHECK pending|confirmed|declined|expired
  expires_at timestamptz NOT NULL
  decided_at timestamptz NULL
Constraints: UNIQUE(tool_execution_id)
Indexes: (tenant_id, status, expires_at)

approvals
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  tool_execution_id uuid NOT NULL FK tool_executions RESTRICT
  status text NOT NULL CHECK pending|approved|rejected|expired
  requested_by_type text NOT NULL CHECK customer|ai|tenant_user|system
  requested_by_id uuid NULL
  approver_user_id uuid NULL FK users RESTRICT
  reason text NOT NULL DEFAULT ''
  expires_at timestamptz NOT NULL
  decided_at timestamptz NULL
Constraints: UNIQUE(tool_execution_id)
Indexes: (tenant_id, status, expires_at), (tenant_id, approver_user_id, status)

support_queues
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  name text NOT NULL CHECK length 1..100
  status text NOT NULL CHECK active|disabled
  sla_first_response_minutes integer NOT NULL CHECK sla_first_response_minutes > 0
Constraints: UNIQUE(tenant_id, name)
Indexes: (tenant_id, status)

escalations
  id uuid PK
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
Indexes: (tenant_id, queue_id, status, priority, created_at), (tenant_id, assigned_user_id, status)

internal_notes
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  conversation_id uuid NOT NULL FK conversations CASCADE
  author_user_id uuid NOT NULL FK users RESTRICT
  content text NOT NULL CHECK length BETWEEN 1 AND 10000
Indexes: (tenant_id, conversation_id, created_at)

feedback
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  conversation_id uuid NOT NULL FK conversations CASCADE
  customer_id uuid NULL FK customers RESTRICT
  rating smallint NOT NULL CHECK rating BETWEEN 1 AND 5
  comment text NULL CHECK length <= 2000
Indexes: (tenant_id, created_at), (tenant_id, conversation_id)

usage_events
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  event_type text NOT NULL
  dimensions jsonb NOT NULL DEFAULT '{}'
  quantity bigint NOT NULL DEFAULT 1
  amount_microusd bigint NULL CHECK amount_microusd >= 0
  occurred_at timestamptz NOT NULL
Indexes: (tenant_id, event_type, occurred_at)

audit_events
  id uuid PK
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
Indexes: (tenant_id, occurred_at DESC), (tenant_id, action, occurred_at DESC), (correlation_id)

idempotency_keys
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  scope text NOT NULL
  idempotency_key text NOT NULL
  request_hash text NOT NULL
  response_status integer NULL
  response_body jsonb NULL
  state text NOT NULL CHECK in_progress|completed|failed
  expires_at timestamptz NOT NULL
Constraints: UNIQUE(tenant_id, scope, idempotency_key)
Indexes: (tenant_id, expires_at)

outbox_events
  id uuid PK
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
Indexes: (status, next_attempt_at), (tenant_id, aggregate_type, aggregate_id)

webhook_endpoints
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  url text NOT NULL
  secret_ref text NOT NULL
  status text NOT NULL CHECK active|disabled
  event_types text[] NOT NULL
  last_validated_at timestamptz NOT NULL
Indexes: (tenant_id, status)

webhook_deliveries
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  webhook_endpoint_id uuid NOT NULL FK webhook_endpoints RESTRICT
  event_id uuid NOT NULL FK outbox_events RESTRICT
  status text NOT NULL CHECK pending|delivered|failed|dead_letter
  attempts integer NOT NULL DEFAULT 0
  last_status_code integer NULL
  next_attempt_at timestamptz NOT NULL DEFAULT now()
  delivered_at timestamptz NULL
Constraints: UNIQUE(webhook_endpoint_id, event_id)
Indexes: (tenant_id, status, next_attempt_at)

platform_feature_flags
  id uuid PK
  flag_key text NOT NULL CHECK length 2..120
  scope_type text NOT NULL CHECK global|tenant
  scope_id text NOT NULL DEFAULT '*'
  enabled boolean NOT NULL
  config jsonb NOT NULL DEFAULT '{}'
  revision bigint NOT NULL DEFAULT 1
  updated_by_operator_id text NOT NULL
Constraints: UNIQUE(flag_key, scope_type, scope_id)
Indexes: (scope_type, scope_id), (flag_key)

rate_limit_policies
  id uuid PK
  limit_key text NOT NULL CHECK length 2..120
  scope_type text NOT NULL CHECK global|tenant|provider
  scope_id text NOT NULL DEFAULT '*'
  route_group text NOT NULL
  actor_dimension text NOT NULL CHECK ip|session|customer|tenant_user|tenant|provider_connection|platform_operator
  window_seconds integer NOT NULL CHECK window_seconds BETWEEN 1 AND 86400
  max_requests integer NOT NULL CHECK max_requests > 0
  concurrency_limit integer NULL CHECK concurrency_limit > 0
  enabled boolean NOT NULL DEFAULT true
  revision bigint NOT NULL DEFAULT 1
  updated_by_operator_id text NOT NULL
Constraints: UNIQUE(limit_key, scope_type, scope_id)
Indexes: (scope_type, scope_id, enabled), (route_group, enabled)

data_subject_requests
  id uuid PK
  tenant_id uuid NOT NULL FK tenants RESTRICT
  customer_id uuid NOT NULL FK customers RESTRICT
  request_type text NOT NULL CHECK export|delete
  status text NOT NULL CHECK pending|processing|completed|failed|cancelled
  requested_at timestamptz NOT NULL DEFAULT now()
  verified_at timestamptz NULL
  completed_at timestamptz NULL
  export_object_key text NULL
  export_expires_at timestamptz NULL
  failure_code text NULL
Indexes: (tenant_id, customer_id, requested_at DESC), (tenant_id, status, requested_at)
```

### 4.3 Tenant Isolation

Application-enforced tenant filtering is mandatory. PostgreSQL RLS is defense in depth where the connection model can set trusted request tenant context safely. No client-supplied tenant ID is authorization. Tenant context is included in relational records, object keys, cache keys, vector/search filters, event envelopes, tool context, and audit records.

### 4.4 Authoritative Ownership for Feature Flags and Rate Limits

This closes the previous storage ambiguity.

- `platform_feature_flags` in PostgreSQL is the authoritative source for global and tenant-scoped platform flags.
- `rate_limit_policies` in PostgreSQL is the authoritative source for configurable platform rate-limit policy.
- Valkey is a derived cache only, with a maximum 60-second TTL plus explicit invalidation after updates. Cache loss never changes the authoritative policy.
- Updates are allowed only through MAS-12 Platform Operations and always create audit events.
- Runtime rate counters live in Valkey. Losing counters may temporarily reduce enforcement precision, so the gateway applies conservative in-process emergency limits until Valkey recovers.
- Configuration reads fail safe: missing or invalid policy uses the frozen built-in default in Section 5.4, never unlimited access.

### 4.5 Privacy, Retention, Export, and Deletion Lifecycle

Production V1 freezes the following defaults. Retention is measured from the relevant terminal time, normally `resolved_at`, `completed_at`, or creation time when no terminal state exists.

| Data class | Default retention | Expiry behavior |
|---|---:|---|
| Customer conversation message content | 90 days after conversation resolution | Delete content and customer-visible metadata not required for audit. |
| Open/unresolved conversation content | While open, then 90 days after resolution | Same as above. |
| Agent step input/output summaries | 30 days after run completion | Delete summaries; retain aggregate usage/audit metadata. |
| Retrieval query text/results | 30 days after run completion | Delete query/result records that contain customer text; knowledge source metadata remains. |
| Normalized tool output containing customer data | 30 days after tool completion unless required by unresolved case | Delete customer-bearing payload; retain outcome/status/audit reference. |
| Escalation handoff content and internal notes | 180 days after resolution | Delete narrative content; retain non-content outcome metrics. |
| Feedback comment | 90 days | Delete comment; aggregate rating may remain anonymized. |
| Usage/analytics events | 400 days | Delete or aggregate/anonymize. |
| Audit events | 400 days minimum | Retain security/business-action record with pseudonymous actor/resource references. Raw secrets/content prohibited. |
| Idempotency records | 24 hours after expiry | Delete. |
| Published outbox events | 7 days | Delete after publication/reconciliation window. |
| Webhook delivery payload metadata | 30 days | Delete delivery detail; aggregate metrics remain. |
| Dead-letter payloads | 14 days unless actively investigated | Delete after investigation window. |
| Application logs | 30 days production default | Delete by log backend lifecycle. |
| Distributed traces | 7 days production default | Delete by tracing backend lifecycle. |
| Metrics | 90 days production default | Downsample/expire according to backend. |
| Provider secret value | Until provider connection deletion/rotation | Delete immediately from secret store on confirmed removal; retain non-secret audit metadata 400 days. |
| Knowledge raw/normalized objects | While source active + 30 days after source deletion | Hard-delete after recovery window. |
| Export artifacts | 7 days after generation; signed download max 24 h | Hard-delete object automatically. |

Customer export/delete workflow:

1. Request is created in `data_subject_requests` only after customer identity verification or an authorized tenant workflow.
2. Export is generated asynchronously from tenant-owned customer data only. Export links use short-lived signed URLs, maximum 24 hours.
3. Export request target completion: within 7 days in V1.
4. Delete request target completion: within 7 days after verification.
5. Delete removes or irreversibly anonymizes direct customer profile fields, customer identity mappings, message content, retrievable customer-bearing step/retrieval/tool payloads, feedback comments, and export artifacts.
6. Audit records required for security and action accountability are retained for their normal retention period but customer identifiers are replaced with a stable one-way pseudonymous reference that cannot be used to rehydrate deleted profile data.
7. Analytics may retain non-identifying aggregate counts after deletion.
8. Production backups use a maximum 30-day retention. Deleted records are not surgically modified inside immutable backups; they expire naturally. Any backup restore procedure must replay the deletion queue before restored data is exposed to users.
9. Customer deletion does not delete tenant-owned public knowledge or workforce records.
10. No legal-hold product UI exists in Production V1. Introducing legal-hold behavior requires a Product Decision and architecture change.

## 5. API Architecture

### 5.1 Base Contract

- Base path: `/api/v1`.
- JSON uses camelCase. Database uses snake_case.
- Lists use `page`, `pageSize`, `sortBy`, `sortOrder`; default `page=1`, `pageSize=25`, max `100`.
- Retriable protected mutations require `Idempotency-Key` where specified by endpoint contract.

Success:

```json
{ "data": {}, "meta": {} }
```

List:

```json
{ "data": [], "meta": { "page": 1, "pageSize": 25, "total": 0, "totalPages": 0 } }
```

Error:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed.",
    "fields": { "fieldName": "Human-readable field error." }
  }
}
```

Standard statuses: 200, 201, 204, 400, 401, 403, 404, 409, 422, 429, 500, and normalized 502/503/504 only when dependency status is part of the endpoint contract.

### 5.2 Endpoint Inventory

**MAS-1 Tenant & Workforce Access**

```text
GET    /api/v1/me
GET    /api/v1/me/memberships
GET    /api/v1/organizations
POST   /api/v1/organizations
GET    /api/v1/organizations/{organizationId}
PATCH  /api/v1/organizations/{organizationId}
GET    /api/v1/organizations/{organizationId}/members
PATCH  /api/v1/organizations/{organizationId}/members/{membershipId}
DELETE /api/v1/organizations/{organizationId}/members/{membershipId}
GET    /api/v1/organizations/{organizationId}/roles
GET    /api/v1/organizations/{organizationId}/invitations
POST   /api/v1/organizations/{organizationId}/invitations
DELETE /api/v1/organizations/{organizationId}/invitations/{invitationId}
POST   /api/v1/invitations/accept
```

Invitation create body:

```json
{ "email": "user@example.com", "roleIds": ["uuid"] }
```

Create response returns invitation metadata plus a one-time `inviteUrl`. The plaintext token is never persisted and is never returned again by list/read APIs. Invitation expiry default is 7 days. Accept requires an authenticated workforce user whose normalized verified email matches the invitation email. Acceptance creates/activates membership and assigned roles transactionally, marks invitation `accepted`, and writes audit/outbox records. Revocation marks a pending invitation `revoked`; expired tokens cannot be accepted.

**MAS-2 Provider Gateway/BYOK**

```text
GET/POST              /api/v1/providers
GET/PATCH/DELETE      /api/v1/providers/{providerConnectionId}
POST                  /api/v1/providers/{providerConnectionId}/test
GET/POST              /api/v1/models
PATCH/DELETE           /api/v1/models/{modelConfigurationId}
```

**MAS-3 Knowledge**

```text
GET/POST              /api/v1/knowledge-sources
GET/PATCH              /api/v1/knowledge-sources/{sourceId}
POST                   /api/v1/knowledge-sources/{sourceId}/sync
POST                   /api/v1/knowledge-sources/{sourceId}/disable
GET                    /api/v1/knowledge-documents
GET                    /api/v1/knowledge-documents/{documentId}
```

**MAS-4 Retrieval**

```text
POST                   /api/v1/retrieval-queries
GET                    /api/v1/retrieval-runs/{retrievalRunId}
```

**MAS-5 Customer Conversation**

```text
POST                   /api/v1/customer/conversations
GET                    /api/v1/customer/conversations/{conversationId}
POST                   /api/v1/customer/conversations/{conversationId}/messages
GET                    /api/v1/customer/conversations/{conversationId}/events
POST                   /api/v1/customer/conversations/{conversationId}/human-request
POST                   /api/v1/customer/conversations/{conversationId}/feedback
```

**MAS-6/MAS-10 Agent Configuration**

```text
GET/POST               /api/v1/agents
GET/PATCH              /api/v1/agents/{agentId}
GET                    /api/v1/agents/{agentId}/versions
POST                   /api/v1/agents/{agentId}/versions
GET                    /api/v1/agent-versions/{agentVersionId}
POST                   /api/v1/agent-versions/{agentVersionId}/evaluate
POST                   /api/v1/agent-versions/{agentVersionId}/publish
POST                   /api/v1/agent-versions/{agentVersionId}/rollback
```

**MAS-7 Tools**

```text
GET                    /api/v1/tools
GET                    /api/v1/tools/{toolId}
POST                   /api/v1/tools/{toolId}/test
GET                    /api/v1/tool-executions/{toolExecutionId}
```

Direct production tool mutation endpoints remain internal; customer mutations originate through the agent/action contract so policy cannot be bypassed.

**MAS-8 Policy/Confirmation/Approval**

```text
GET/POST               /api/v1/policies
GET                    /api/v1/policies/{policyId}
POST                   /api/v1/policies/{policyId}/versions
POST                   /api/v1/customer/action-confirmations/{confirmationId}/confirm
POST                   /api/v1/customer/action-confirmations/{confirmationId}/decline
GET                    /api/v1/approvals
GET                    /api/v1/approvals/{approvalId}
POST                   /api/v1/approvals/{approvalId}/approve
POST                   /api/v1/approvals/{approvalId}/reject
```

**MAS-9 Human Support**

```text
GET                    /api/v1/support-queues
GET                    /api/v1/escalations
GET                    /api/v1/escalations/{escalationId}
POST                   /api/v1/escalations/{escalationId}/assign
POST                   /api/v1/escalations/{escalationId}/reassign
POST                   /api/v1/escalations/{escalationId}/resolve
POST                   /api/v1/escalations/{escalationId}/reopen
POST                   /api/v1/conversations/{conversationId}/messages
POST                   /api/v1/conversations/{conversationId}/internal-notes
```

**MAS-11 Analytics/Audit/Privacy**

```text
GET                    /api/v1/analytics/overview
GET                    /api/v1/analytics/providers
GET                    /api/v1/analytics/tools
GET                    /api/v1/analytics/retrieval
GET                    /api/v1/audit-events
GET                    /api/v1/audit-events/{auditEventId}
POST                   /api/v1/customer/privacy/export
POST                   /api/v1/customer/privacy/delete
GET                    /api/v1/customer/privacy/requests/{requestId}
```

**MAS-12 Platform Operations**

```text
GET                    /api/v1/platform/tenants
GET                    /api/v1/platform/tenants/{tenantId}
GET                    /api/v1/platform/health
GET                    /api/v1/platform/providers
GET                    /api/v1/platform/queues
GET                    /api/v1/platform/jobs
GET                    /api/v1/platform/dead-letters
GET                    /api/v1/platform/feature-flags
PATCH                  /api/v1/platform/feature-flags/{flagKey}
GET                    /api/v1/platform/rate-limits
PATCH                  /api/v1/platform/rate-limits/{limitKey}
GET                    /api/v1/platform/usage
GET                    /api/v1/platform/security-events
```

### 5.3 SSE Contract

`GET /api/v1/customer/conversations/{conversationId}/events` returns `text/event-stream` with only:

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

Payload:

```json
{
  "eventId": "evt_...",
  "conversationId": "uuid",
  "type": "message.delta",
  "occurredAt": "ISO-8601",
  "data": {}
}
```

Internal reasoning, raw prompts, secrets, unrestricted tool output, evidence scores, and policy internals are prohibited from customer streams.

### 5.4 Frozen Production V1 Rate-Limit Defaults

The authoritative configurable representation is `rate_limit_policies`. These built-in defaults are used if the configuration store is missing or invalid. Limits are enforced at the edge/API boundary and can also be reinforced inside expensive services.

| Limit key | Dimension | Default |
|---|---|---:|
| `auth.login` | IP + normalized login identifier | 10 attempts / 15 min |
| `customer.conversation.create.ip` | IP | 20 / min |
| `customer.conversation.create.customer` | verified customer | 60 / min |
| `customer.message.session` | anonymous/verified session | 30 / min |
| `customer.message.customer` | verified customer | 60 / min |
| `customer.message.ip` | IP | 300 / min, burst 60/10s |
| `provider.test.user` | tenant user | 10 / min |
| `provider.test.connection` | provider connection | 30 / hour |
| `provider.call.concurrent.connection` | provider connection | 20 concurrent unless provider/account configuration is lower |
| `knowledge.upload.user` | tenant user | 30 / hour |
| `knowledge.sync.tenant` | tenant | 60 / hour, max 5 concurrent |
| `agent.evaluate.user` | tenant user | 20 / min |
| `agent.evaluate.tenant` | tenant | 100 / hour |
| `privacy.export.customer` | customer | 3 / 24 h |
| `privacy.delete.customer` | customer | 2 / 24 h |
| `webhook.config.user` | tenant user | 30 / min |
| `platform.control.operator` | platform operator | 60 / min |

429 response includes `Retry-After` and stable error code `RATE_LIMITED`. Rate-limit keys never include raw email, API key, token, or other secret. Login identifiers are normalized and keyed through a server-side one-way digest.

## 6. Auth & Permissions

### 6.1 Workforce Authentication

1. Unauthenticated workforce user is redirected to OIDC Authorization Code + PKCE.
2. Callback establishes a server-managed Serviq session; provider access/refresh tokens stay server-side.
3. Browser receives opaque/encrypted `HttpOnly`, `SameSite=Lax`, `Secure` in production cookie.
4. API resolves user and membership from trusted session state.
5. Tenant route context is validated against membership; arbitrary tenant headers are never trusted.
6. Capability guard checks required permission.
7. Service/repository layer enforces tenant/object ownership.

### 6.2 Customer Identity

Anonymous support is allowed only where tenant channel policy permits it. Protected customer data/actions require a tenant-signed short-lived assertion or configured identity integration. Assertion validates tenant, issuer, subject, audience, expiry, signature, and assurance level before mapping to `customer_identities`.

### 6.3 Platform Operators

Platform operators use a separate trust boundary and cannot receive operator permissions through tenant role APIs. Every tenant-detail access by an operator is audited with reason/context where the operation contract requires it.

### 6.4 Premium Review Required

Auth/session flows, invitation token handling, permission middleware, customer identity assertions, RLS policies, rate limiting, privacy deletion, platform-operator tenant access, and secret management require premium security review before merge.

## 7. Background Jobs

| Job | Trigger/topic | Retry | Idempotency |
|---|---|---|---|
| Outbox publish | DB poll | continuous exponential on broker failure | `outbox_event.id` |
| Knowledge sync | `serviq.knowledge.sync.v1` | 30s, 5m, 30m then DLQ | `tenantId:sourceId:syncVersion` |
| Document parse | `serviq.knowledge.parse.v1` | 30s, 5m, 30m then DLQ | `documentId:documentVersion` |
| Chunk/embed/index | `serviq.knowledge.index.v1` | 1m, 10m, 30m then DLQ | document/version/profile |
| Analytics projection | `serviq.analytics.events.v1` | 5 exponential retries then DLQ | source event ID |
| Webhook delivery | `serviq.webhooks.delivery.v1` | 8 exponential+jitter retries, max 24h | endpoint:event |
| Notification | `serviq.notifications.v1` | 5 retries then DLQ | command ID |
| Tool reconciliation | `serviq.tools.reconcile.v1` | 5 retries up to 30m then escalation | toolExecutionId |
| Approval expiry | minute scheduler | repeat-safe | approvalId:expiresAt |
| Confirmation expiry | minute scheduler | repeat-safe | confirmationId:expiresAt |
| Privacy export | `serviq.privacy.export.v1` | 3 retries then failed | requestId |
| Privacy delete | `serviq.privacy.delete.v1` | 3 retries; partial progress resumable | requestId |
| Retention purge | daily scheduler | repeat-safe | class:cutoffDate |
| Dead-letter replay | explicit operator action | one replay command | original ID + replay sequence |

All durable jobs are idempotent, observable, bounded, and survive process failure.

## 8. File Storage

Local bucket: `serviq-local-objects`. Cloud convention: `serviq-{environment}-objects`.

```text
tenants/{tenantId}/knowledge/{sourceId}/raw/{objectId}
tenants/{tenantId}/knowledge/{sourceId}/normalized/{documentId}/{version}
tenants/{tenantId}/exports/{exportId}
tenants/{tenantId}/evaluation/{evaluationRunId}
```

User filenames are metadata only, never object keys.

Allowed knowledge uploads:

| Type | Extensions | MIME | Max |
|---|---|---|---:|
| PDF | `.pdf` | `application/pdf` | 25 MiB |
| Markdown | `.md`, `.markdown` | `text/markdown`, `text/plain` | 5 MiB |
| Text | `.txt` | `text/plain` | 5 MiB |

Extension, MIME, and content sanity must pass. Files are treated as untrusted data and never executed.

`Needs Product Decision: End-customer attachments remain disabled until PRD Section 16 resolves their V1 scope.`

## 9. Integrations

### 9.1 LLM Providers

OpenAI, Anthropic, Gemini, and OpenRouter are accessed only through the Serviq gateway. Credentials are server-side BYOK secret references. Calls use explicit timeouts, normalized errors, provider health/circuit state, and ordered fallback if configured and within run budget.

### 9.2 Keycloak OIDC

Local/dev workforce identity. Authorization Code + PKCE. Identity outage never bypasses validation or authorization.

### 9.3 Public Knowledge Fetcher

HTTPS by default. Before each fetch and after every redirect, resolve and reject loopback, link-local, RFC1918/private, metadata, multicast, reserved, and prohibited IPv4/IPv6 targets. Apply domain allowlist, response-size limit, content-type allowlist, timeout, crawl rate, and access/terms restrictions. Never bypass authentication or anti-bot/access controls.

For the OPE-251 reference configuration, `doordash-stripe-allowlist-v1` is the only approved source-manifest policy name. DoorDash is the primary customer-support/delivery reference domain and Stripe is a separate payment/refund reference domain. This choice does not grant Serviq permission to crawl either site broadly. Each source entry must be explicitly approved/permitted for the intended ingestion path. If automated access is not permitted, the source is disabled and only an allowed/manual/permitted alternative may be used.

### 9.4 Synthetic Demo Operational Adapter

The Production V1 reference adapter is frozen by CCR-003 and combines a DoorDash reference customer-support/delivery domain with a separate Stripe reference payment domain. It is a Serviq-owned synthetic adapter and does not assert or depend on any real DoorDash-to-Stripe integration.

Required synthetic entity families are:

```text
demo_customers
demo_orders
demo_order_items
demo_deliveries
demo_order_events
demo_payments
demo_refund_rules
demo_refunds
demo_support_cases
```

The first tool keys are exactly:

```text
demo.get_delivery_order_status
demo.check_order_resolution_eligibility
demo.create_refund
```

- `demo.get_delivery_order_status` is read-only and returns verified synthetic order/delivery state.
- `demo.check_order_resolution_eligibility` is read-only and evaluates synthetic order/item/delivery/payment state plus Serviq demo policy.
- `demo.create_refund` is a protected idempotent mutation that changes only Serviq synthetic refund state in deterministic V1 development/CI.

The deterministic V1 demo never accesses DoorDash private systems, never uses real customer/payment PII, never calls a production Stripe account, and never moves real money. The adapter must support deterministic failures, timeout simulation, and ambiguous-mutation simulation for reconciliation tests. A later ticket may add an optional Stripe test-mode adapter behind the same Serviq tool contract without changing agent/policy semantics.

### 9.5 Outbound Tenant Webhooks — Frozen SSRF/Egress Contract

This closes the previous webhook SSRF gap.

**Endpoint creation/update validation**

- Production V1 accepts `https://` only.
- URL username/password syntax is rejected.
- URL fragments are rejected.
- Production V1 allows port 443 only. Additional ports require an architecture change.
- DNS is resolved server-side. Reject loopback, link-local, RFC1918/private, carrier-grade NAT, metadata, multicast, documentation/reserved, and non-routable IPv4/IPv6 ranges.
- Hostnames resolving to any prohibited address are rejected.
- Validation success stores `last_validated_at`, not a trusted forever-resolved IP.

**Delivery-time protection**

- DNS is resolved again immediately before every delivery attempt to prevent DNS-rebinding bypass.
- The connected peer address must be public and must match an allowed result of the just-performed resolution.
- HTTP redirects are disabled for webhook delivery.
- Connect timeout: 5 seconds. Total request timeout: 10 seconds.
- Response body read limit: 64 KiB. Larger bodies are truncated/discarded and never passed to the model.
- Outbound proxy/environment settings must not allow tenants to bypass target validation.
- HMAC signature secret remains server-side. Signature includes event ID, timestamp, and raw request body; receiver replay window target is 5 minutes.
- Delivery is asynchronous, duplicate-safe, bounded, and dead-lettered after retry exhaustion.

**Local development exception**

Local Docker profile may allow explicit `http://host.docker.internal:<configured-dev-port>` only when `SERVIQ_ENV=local` and an explicit development allowlist is set. This exception is impossible in staging/production configuration validation.

Webhook URL validation, delivery egress controls, and HMAC implementation require premium security review.

## 10. Observability

### 10.1 Logging

Structured JSON fields: timestamp, level, service, requestId, traceId, spanId, tenantId when safe, pseudonymous actor ID when necessary, route/job/event, errorCode, message. Never log passwords, tokens, cookies, API keys, raw customer secrets, full prompts containing PII, or unrestricted tool output.

### 10.2 Metrics

Minimum metrics include request rate/latency/error, SSE connections, DB pool saturation, cache hit/miss, rate-limit decisions, queue lag, dead letters, agent duration/steps/model/tool calls, retrieval latency/results, provider latency/errors/429s, tool outcomes/unknown state, escalation/resolution, knowledge backlog, webhook delivery failures, privacy request age, and purge failures.

### 10.3 Tracing

One distributed trace covers ingress -> auth/tenant -> persistence -> agent -> retrieval/provider/policy/tool -> response -> outbox/audit. Secrets and raw sensitive content are excluded.

### 10.4 Health

```text
GET /health/live
GET /health/ready
GET /health/info
```

Readiness checks required infrastructure for that process but never performs expensive provider calls.

## 11. Deployment Assumptions

Environments: `local`, `test`, `staging`, `production`.

Required initial environment names:

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
SERVIQ_LOCAL_WEBHOOK_ALLOWLIST
```

`SERVIQ_LOCAL_WEBHOOK_ALLOWLIST` is ignored/rejected outside `local`.

Root commands must be equivalent to:

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

CI runs deterministic fake LLM/tool providers and does not require paid external calls.

## 12. System Boundaries & Contracts

### CONTRACT C-1 — Trusted Auth/Tenant Context

```json
{
  "requestId": "string",
  "tenantId": "uuid",
  "actor": { "type": "tenant_user|customer|service|platform_operator", "id": "string" },
  "userId": "uuid|null",
  "customerId": "uuid|null",
  "permissions": ["string"],
  "assuranceLevel": "anonymous|verified|workforce|platform"
}
```

Owner: MAS-1. Missing identity 401, missing permission 403, inaccessible object 404 where non-disclosure applies.

### CONTRACT C-2 — Conversation -> Agent Runtime

Event `agent.run.requested` on `serviq.agent.runs.v1`:

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

Owner: MAS-5 produces; MAS-6 consumes idempotently.

### CONTRACT C-3 — Agent <-> Retrieval

Request:

```json
{ "tenantId": "uuid", "query": "string 1..4000", "accessScope": "customer|internal", "topK": 10, "sourceIds": ["uuid"], "knowledgeVersion": null }
```

Response contains ranked `chunkId`, `documentId`, `sourceId`, `content`, `score`, citation title/URI/location, and `retrievalRunId`. Errors: `RETRIEVAL_UNAVAILABLE`, `INVALID_RETRIEVAL_QUERY`. Owner: MAS-4.

### CONTRACT C-4 — Agent <-> LLM Gateway

Request includes tenantId, modelAlias, purpose, messages, responseSchema, maxOutputTokens, timeoutMs, stream, correlationId. Response normalizes content/structured output, provider, upstream model, usage, finish reason, request ID. Errors: `PROVIDER_RATE_LIMITED`, `PROVIDER_TIMEOUT`, `PROVIDER_UNAVAILABLE`, `PROVIDER_INVALID_REQUEST`, `PROVIDER_AUTH_FAILED`. Owner: MAS-2.

### CONTRACT C-5 — Agent -> Tool Proposal

```json
{ "tenantId": "uuid", "agentRunId": "uuid", "toolKey": "string", "toolVersion": 1, "arguments": {}, "customerId": "uuid|null", "correlationId": "string" }
```

Arguments validate against frozen JSON Schema. Unknown fields fail `TOOL_ARGUMENT_VALIDATION_FAILED`. Owner: MAS-7.

### CONTRACT C-6 — Tool -> Policy

Input includes toolExecutionId, tool/risk, customer assurance, arguments, context. Response:

```json
{ "decision": "allow|deny|require_confirmation|require_human_approval", "policyVersionId": "uuid", "reasonCode": "string", "confirmationExpiresAt": "iso8601|null", "approvalExpiresAt": "iso8601|null" }
```

Missing mutation policy means deny. Owner: MAS-8.

### CONTRACT C-7 — Approval -> Human Support

Event `approval.requested` on `serviq.support.approvals.v1` includes approvalId, conversationId, toolExecutionId, riskClass, reasonCode, expiresAt, correlationId. MAS-9 displays/assigns; MAS-8 alone changes decision state.

### CONTRACT C-8 — Agent -> Escalation

Command includes tenantId, conversationId, optional agentRunId, reasonCode, priority, evidenceChunkIds, toolExecutionIds, recommendedNextAction. Response returns escalationId, queueId, status. Owner: MAS-9.

### CONTRACT C-9 — Knowledge -> Retrieval Index

Event `knowledge.document.indexed` on `serviq.knowledge.events.v1` includes tenantId, sourceId, documentId, documentVersion, contentHash, chunkCount, embeddingModelAlias, correlationId. Owner: MAS-3.

### CONTRACT C-10 — All MASs -> Audit

Event `audit.event.recorded` on `serviq.audit.events.v1` includes eventId, schemaVersion, tenantId nullable, actor, action, resource, outcome, allow-listed metadata, correlationId, occurredAt. No secrets. Owner: MAS-11 persistence/query.

### CONTRACT C-11 — All MASs -> Analytics

Event `usage.recorded` on `serviq.analytics.events.v1` includes eventId, tenantId, eventType, quantity, amountMicrousd nullable, dimensions, occurredAt. Analytics failures never block customer response.

### CONTRACT C-12 — Customer SSE

Only Section 5.3 public event types may reach the customer. Owner: MAS-5.

### CONTRACT C-13 — Organization Invitation

Create request:

```json
{ "email": "string <=320", "roleIds": ["uuid"] }
```

Create response:

```json
{
  "data": {
    "id": "uuid",
    "email": "normalized@example.com",
    "roleIds": ["uuid"],
    "status": "pending",
    "expiresAt": "iso8601",
    "inviteUrl": "string"
  },
  "meta": {}
}
```

`inviteUrl` is returned once. Database stores only token hash. Acceptance body is `{ "token": "string" }`; authenticated verified email must match. Owner: MAS-1.

### CONTRACT C-14 — Platform Feature/Rate Configuration

Authoritative database: `platform_feature_flags`, `rate_limit_policies`. Runtime cache: Valkey derived cache max TTL 60s. Every write increments `revision`, invalidates cache, emits audit event. Owner: MAS-12. All consumers treat missing/invalid config as frozen default rather than unlimited.

### CONTRACT C-15 — Privacy Request

Export/delete request is tenant/customer scoped and requires verified identity. Async job uses `data_subject_requests.id` as idempotency key. Export artifact max lifetime 7 days, signed URL max 24h. Delete follows Section 4.5 and cannot delete/rewrite immutable audit history beyond pseudonymization rules. Owner: MAS-11 Privacy module.

### CONTRACT C-16 — Production V1 Reference Demo Composition

OPE-251 / CCR-003 freezes the following implementation identifiers:

```text
demoCompany = "DoorDash reference support domain"
paymentProvider = "Stripe reference payment domain"
publicSourceManifestPolicy = "doordash-stripe-allowlist-v1"
statusToolKey = "demo.get_delivery_order_status"
eligibilityToolKey = "demo.check_order_resolution_eligibility"
mutationToolKey = "demo.create_refund"
```

Required synthetic record families: `demo_customers`, `demo_orders`, `demo_order_items`, `demo_deliveries`, `demo_order_events`, `demo_payments`, `demo_refund_rules`, `demo_refunds`, `demo_support_cases`.

The DoorDash and Stripe references are independent reference domains; the architecture makes no claim that DoorDash uses Stripe. Public-source ingestion is explicit-allowlist only and may not bypass access controls. The deterministic Production V1 mutation modifies only synthetic Serviq data. Owner: MAS-7, with MAS-3/4 source/evaluation dependencies and MAS-8 policy governance.

## 13. Parallelization Map

### Phase 0 — Foundation

Repository scaffold, Docker Compose, CI/security baseline, shared API/error contracts, migration harness, auth skeleton, rate-limit middleware skeleton, observability, and `docs/repo_context.md`.

### Phase 1 — Parallel Foundations

- MAS-1 Tenant/Auth/Invitations.
- MAS-2 Provider/BYOK against mocked tenant context.
- MAS-3 Knowledge lifecycle.
- MAS-5 Conversation persistence/stream shell.
- MAS-11 Audit/privacy persistence foundation.
- MAS-12 Feature/rate configuration persistence may start after MAS-1 platform identity stub.

### Phase 2 — Intelligence and Governance

- MAS-4 after MAS-3 contract.
- MAS-6 against MAS-2/MAS-4/MAS-5 mocks/contracts.
- MAS-7 may proceed against the frozen OPE-251 / CCR-003 reference contract and no longer has a demo-domain Product Decision blocker.
- MAS-8 after MAS-7 schemas and MAS-1 auth.

### Phase 3 — Human and Management

- MAS-9 after MAS-5/MAS-6/MAS-8.
- MAS-10 builds against frozen API mocks then integrates.
- MAS-11 analytics expands as source events stabilize.

### Phase 4 — Operations and Hardening

- MAS-12 consumes health/audit/queue/provider contracts.
- MAS-13 performs security, contract drift, migration, privacy, failure, E2E, and load gates.

## 14. Risk Register

| Area | Risk | Required handling |
|---|---|---|
| Workforce auth/session | Session compromise exposes tenant data | Premium review; OIDC standard flow; no browser token storage; auth failure tests. |
| Invitations | Token leakage or email mismatch grants membership | Hash tokens, one-time return, short expiry, verified-email match, revoke path, premium review. |
| Tenant authorization/RLS | Cross-tenant leakage | Premium review; tenant-scoped queries, RLS defense, adversarial isolation tests. |
| Customer identity | Forged assertion exposes private records | Premium review; signed short-lived assertions, issuer/audience/expiry checks. |
| BYOK secrets | Key exposure creates billing/security risk | Secret adapter, encryption, masking, redaction, premium review. |
| Public ingestion | SSRF, malware, prompt injection, legal/source issues | Network checks, redirect re-check, content limits, untrusted boundary, explicit source allowlist/access checks, premium review. |
| Outbound webhooks | SSRF/DNS rebinding or forged callbacks | HTTPS/443 only, resolve each delivery, peer-IP validation, no redirects, HMAC, premium review. |
| Rate limiting | Bypass or accidental tenant-wide denial | Frozen defaults, authoritative DB config, derived cache, conservative fallback, premium review. |
| Privacy deletion | Partial deletion leaves PII or destroys required audit | Resumable idempotent purge, pseudonymized audit, backup replay procedure, premium review. |
| LLM user/retrieved data | Prompt injection or PII leakage | Separate instructions/data, minimize context, validate structured output, no raw prompt logs. |
| Tool mutations | Duplicate or unauthorized side effects | Policy first, idempotency, reconciliation, approval, premium review. |
| Migrations | Data loss/schema drift | Expand/migrate/contract, tested rollback, premium review for destructive/large changes. |
| Event concurrency | Duplicate/out-of-order processing | Outbox, idempotent consumers, partition keys, version/sequence checks. |
| Vector retrieval | Dimension/model drift | Freeze embedding profile ADR before production vector index. |
| Observability | PII/cardinality leakage | Redaction, pseudonymous IDs, bounded labels, retention defaults. |
| 10M concurrency target | Premature complexity/false claims | Preserve seams, scale from measured bottlenecks, publish reproducible benchmarks. |
| Local resource use | Full stack too heavy | Compose profiles and deterministic mocks. |

### Architecture Product Decisions

Resolved by OPE-251 / CCR-003:

- first public customer-support reference domain: DoorDash support/delivery reference;
- separate payment-provider reference domain: Stripe payment/refund reference;
- matching synthetic private-data/tool domain and the three MAS-7 tool keys.

Still blocked:

- `Needs Product Decision: Resolve end-customer attachment scope before any customer upload endpoint, object path, validation rule, or UI is created.`

Builders must not guess the remaining attachment decision. The OPE-251 demo-domain decision is no longer blocked.

## V1.3.04A durable knowledge-upload consistency contract

ADR-018 and CCR-006 freeze the cross-store raw-upload boundary. Before any raw object PUT, the API commits a tenant-scoped `knowledge_upload_cleanups` row containing generated source/object identity and the typed raw key. A confirmed successful PUT is followed by one PostgreSQL transaction that creates the normal `knowledge_sources` row and changes cleanup to `referenced` atomically.

Storage I/O is never performed while the cleanup/source transaction is open. Confirmed source-persistence failure keeps the durable intent, schedules first replay after 30 seconds, and may perform one immediate idempotent delete as a fast path. Background failures retry after 5 minutes and 30 minutes; the third failed replay becomes `exhausted`.

A generic PUT error is outcome-ambiguous. Its `prepared` intent remains durable for a 15-minute grace period and due reconciliation uses the typed `exists`/HEAD operation before deciding whether deletion is required. The same bounded observation/retry budget applies when presence cannot be safely resolved.

Replay is tenant-scoped and regenerates the expected typed key from tenant/source/object identity. A key mismatch fails closed. Structured state logs and internal status counts omit object keys, file contents, credentials, and tokens. No public cleanup API is added.

Resolved `referenced`/`succeeded` rows are eligible for a future purge after 14 days; unresolved and `exhausted` work is retained for reconciliation/operator recovery. Alembic downgrade refuses to drop the table while unresolved `prepared`, `pending`, or `exhausted` obligations exist.

This preserves the existing knowledge-upload HTTP envelope, supported file rules, RBAC behavior, tenant-visible source listing, and raw object-key layout. General outbox/broker integration remains future work.

