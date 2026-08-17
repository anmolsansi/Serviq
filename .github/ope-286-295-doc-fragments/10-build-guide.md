---

# OPE-286 through OPE-295 — final implementation reconciliation

This reconciliation records the final, actually merged state of the ten-ticket OPE-286 through OPE-295 batch. It complements the detailed ticket narratives in this build guide and `docs/OPE_286_295_IMPLEMENTATION_GUIDE.md`.

The important distinction is **merged and validated on `main`**, not merely “code existed on a feature branch.” During this batch several earlier stacked branches had to be rebuilt cleanly, and permanent CI found real defects that were corrected before merge.

## Final ticket-by-ticket status

### OPE-286 — invitation acceptance

**GitHub issue #98, merged PR #108, Linear Done.**

Serviq can accept a valid pending workforce invitation atomically after authenticated identity and verified email checks. The flow protects single-use invitation semantics, tenant-safe role assignment, token-hash handling, and concurrent acceptance behavior. The practical improvement is that the invitation lifecycle is now complete enough to turn an issued invite into real organization membership safely.

### OPE-287 — member list and role/status management

**GitHub issue #99, merged PR #109, Linear Done.**

Authorized Owners/Admins can list tenant members and update allowed membership roles/status without crossing tenant boundaries. The service enforces role allowlisting and protects the last active Owner from being removed or suspended. The practical improvement is a real backend foundation for Team & Access administration instead of invitations only.

### OPE-288 — reusable tenant-isolation harness

**GitHub issue #100, merged PR #110, Linear Done.**

The real PostgreSQL test suite now has reusable adversarial tenant-A/tenant-B fixtures, deliberately overlapping visible values, known foreign UUID attacks, and persisted-state assertions. The practical improvement is that future tenant-owned domains can prove isolation using a common hostile test pattern instead of writing weak one-off tests.

### OPE-289 — provider/model metadata

**GitHub issue #101, merged PR #116, Linear Done.**

PostgreSQL now has `provider_connections` and `model_configurations`. Provider rows contain safe metadata and an opaque `secret_ref`, never a plaintext provider key. Model aliases are tenant-scoped and decouple product/agent code from provider model strings. The practical improvement is a database-enforced BYOK/model configuration foundation.

### OPE-290 — tenant secret adapter

**GitHub issue #102, merged PR #117, Linear Done.**

Serviq now has a `TenantSecretStore` abstraction plus a real encrypted local implementation. Secrets are referenced by random opaque IDs, encrypted before disk persistence, tenant-bound, redacted from representation/errors, and written atomically. The practical improvement is a credential boundary that can later be replaced with a managed secret service without rewriting provider-management code.

### OPE-291 — provider connection CRUD

**GitHub issue #103, merged PR #118, Linear Done.**

Authorized tenant users can create/list/read/update/delete BYOK provider connections. The API uses trusted tenant context, `ai.providers.manage`, encrypted secret-store coordination, row locking for replacement/deletion-sensitive operations, safe compensation/cleanup, and provider-in-use protection. Plaintext API keys are never returned.

The clean mainline rebuild was important: CI exposed incorrect module imports, the wrong ORM base reference, a FastAPI 204 response-contract problem, secret-store dependency drift, and a tuple/list API type mismatch. Each was fixed and the full matrix rerun before merge.

### OPE-292 — normalized C-4 gateway contract

**GitHub issue #104, merged PR #119, Linear Done.**

The LLM Gateway now owns strict provider-neutral request, response, usage, streaming, and error models. It freezes token/timeout hard ceilings and exactly five normalized provider failure categories. Agents/domain code can depend on Serviq types rather than provider SDK types.

### OPE-293 — deterministic fake LLM adapter

**GitHub issue #105, merged PR #121, Linear Done.**

The shared `LLMAdapter`/`AdapterContext` boundary and deterministic fake provider make AI success, streaming, malformed-output, timeout, rate-limit, unavailable, and auth-failure tests reproducible with zero paid calls and zero network dependency. ADR-010 keeps fake behavior out of the public provider enum.

The fake streaming tests also uncovered a shared C-4 correctness issue: global string trimming could corrupt provider-generated chunks. That was corrected separately in PR #123 so request identifiers remain normalized while provider output text is preserved exactly.

### OPE-294 — OpenAI adapter

**GitHub issue #106, merged PR #124, Linear Done.**

After ADR-011 froze `openai==2.53.0`, the official SDK adapter was implemented behind C-4. It supports non-stream text, JSON Schema structured output, ordered streaming, usage/finish/request ID normalization, bounded time/output tokens, safe BYOK handling, `max_retries=0`, and full C-4 error normalization.

Tests inject mocked SDK clients and make no paid OpenAI call. Strict mypy caught a request/output SDK type mismatch during validation; the final implementation uses the actual request parameter types.

### OPE-295 — Anthropic adapter

**GitHub issue #107, merged PR #125, Linear Done.**

After ADR-011 froze `anthropic==0.121.0`, the Anthropic adapter was added behind the same C-4 interface. Leading C-4 system messages are translated to Anthropic's top-level system field while user/assistant history remains ordered. Unsupported late system messages fail explicitly rather than being silently reordered.

The adapter supports non-stream generation, JSON Schema structured output, text/structured streaming, usage/stop/request ID normalization, bounded calls, disabled hidden retries, safe BYOK handling, and the same five provider-neutral error categories. Mocked tests make no live Anthropic call.

## Supporting decisions/fixes that were required to finish the batch

### PR #122 — official provider SDK baseline

The original OPE-294/OPE-295 tickets correctly stopped because no approved official provider SDK version existed in the repository. ADR-011 resolved that prerequisite before feature implementation by pinning:

```text
openai==2.53.0
anthropic==0.121.0
```

SDK classes are restricted to provider adapters/tests. C-4 remains Serviq-owned, and API keys enter adapters only through server-resolved context.

### PR #123 — preserve generated text

C-4 originally used one whitespace-trimming Pydantic base for both request identifiers and provider output. That could change streamed model text such as `" world"` into `"world"`.

PR #123 introduced an output-specific strict base that does not strip generated text. This is a correctness fix, not a provider-specific extension: the C-4 field set, provider enum, and budgets did not change.

## Validation discipline

Across the final PRs, merge required the repository's permanent quality/security gates:

- frontend/Python lint;
- strict TypeScript/Python type checking;
- unit/contract tests;
- Docker Compose validation;
- real PostgreSQL integration tests;
- migration upgrade/downgrade/re-upgrade coverage;
- Trivy filesystem/configuration scanning;
- dependency vulnerability audit;
- Gitleaks history/tree secret scanning;
- Python CodeQL;
- JavaScript/TypeScript CodeQL.

Transient GitHub action-download HTTP 429 failures were rerun unchanged. Code/security rules were not weakened to turn infrastructure noise green.

## Clean-branch reconciliation

Several OPE-289 through OPE-293 implementations originally existed as stacked PRs. As predecessor tickets were squash-merged, those historical stacks polluted later diffs with already-merged files.

The final implementations were rebuilt from the real mainline so the authoritative PRs contain only the intended ticket delta:

- OPE-289 -> PR #116;
- OPE-290 -> PR #117;
- OPE-291 -> PR #118;
- OPE-292 -> PR #119;
- OPE-293 -> PR #121.

Superseded stacked PRs remain historical evidence but are not the merged source of truth.

## What the ten-ticket batch changes overall

After OPE-286 through OPE-295, Serviq now has:

- complete workforce invitation acceptance;
- protected member/role/status administration;
- reusable tenant-isolation adversarial tests;
- provider/model metadata with no relational plaintext provider keys;
- a tenant-scoped secret-store contract and encrypted local adapter;
- tenant-scoped BYOK provider CRUD;
- one strict provider-neutral LLM gateway contract;
- deterministic offline AI testing;
- an official OpenAI adapter;
- an official Anthropic adapter.

This is a major V1 production-foundation step, but it is not the end of the AI platform. Gemini/OpenRouter adapters, provider connectivity testing, model-configuration CRUD/alias resolution, runtime provider routing/fallback, knowledge ingestion, agent workflows, production managed secret storage, and later observability/deployment work remain separate tickets.

## Completion evidence

| Linear ticket | GitHub issue | Final merged PR | Result |
|---|---:|---:|---|
| OPE-286 | #98 | #108 | Invitation acceptance |
| OPE-287 | #99 | #109 | Member/RBAC management |
| OPE-288 | #100 | #110 | Tenant-isolation test harness |
| OPE-289 | #101 | #116 | Provider/model metadata schema |
| OPE-290 | #102 | #117 | Tenant secret-store adapter |
| OPE-291 | #103 | #118 | Provider connection CRUD |
| OPE-292 | #104 | #119 | C-4 normalized gateway contract |
| OPE-293 | #105 | #121 | Deterministic fake LLM adapter |
| OPE-294 | #106 | #124 | OpenAI adapter |
| OPE-295 | #107 | #125 | Anthropic adapter |

Supporting merged PRs: **#122** (provider SDK architecture baseline) and **#123** (C-4 provider-output whitespace correctness).

All ten Linear tickets are `Done`, all ten feature implementations are merged to `main`, and this documentation records what changed, why it changed, what it improves, how it was validated, and what remains intentionally outside the batch.
