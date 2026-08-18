# OPE-298 — Premium security review: provider connectivity test

## Review result

**Approved for merge after repository CI and Security workflows are green.**

This review covers the OPE-298 implementation of:

```text
POST /api/v1/providers/{providerConnectionId}/test
```

and its private API-to-LLM-Gateway control path:

```text
POST /internal/v1/provider-connectivity-test
```

The purpose of this review is to challenge the implementation as if an attacker, a buggy client, a provider outage, a concurrent key rotation, or a horizontally scaled deployment were trying to make the feature behave incorrectly.

The architecture authority for the implementation is ADR-014.

---

## 1. Threat: turning a health check into a free-form LLM proxy

### Risk

A provider-test endpoint can accidentally become a hidden completion API if a caller can submit fields such as:

- prompt;
- model;
- provider URL;
- output-token limit;
- timeout;
- headers;
- response schema;
- streaming options.

That would bypass normal agent/model configuration, make cost controls unreliable, and create an SSRF/arbitrary-endpoint risk if the caller could influence a base URL.

### Control implemented

The public route has **no request-body model** and explicitly rejects any non-empty request body with a safe `422` response.

The LLM-Gateway private schema uses `extra="forbid"`, so even a trusted internal caller cannot add arbitrary `model`, `prompt`, or `baseUrl` fields.

The gateway itself creates the only provider request:

- fixed text: `Reply with OK.`;
- one user message;
- 4 output tokens maximum;
- 5-second provider timeout;
- non-streaming;
- no caller response schema.

The provider-to-test-model mapping lives in gateway code and is selected only from the stored provider enum.

### Verification

Tests verify that:

- the public endpoint rejects arbitrary body fields without invoking the provider gateway;
- the private route rejects extra model/prompt/baseUrl fields;
- each supported provider maps to its frozen server-owned test model;
- the generated provider content is discarded rather than returned.

### Review conclusion

**Pass.** OPE-298 does not create a new caller-controlled completion surface.

---

## 2. Threat: arbitrary provider endpoint / SSRF

### Risk

If a caller can provide or influence an upstream URL, the server could be tricked into contacting internal infrastructure or attacker-controlled hosts.

### Control implemented

The public request accepts no URL.

The private gateway request accepts no URL.

The API's service-to-service destination is built only from the architecture-owned `LLM_GATEWAY_URL` platform setting plus the hard-coded path:

```text
/internal/v1/provider-connectivity-test
```

Provider adapters continue using the endpoint rules already approved in their own ADRs and implementations. OPE-298 does not add an adapter base-URL override.

HTTP redirects are disabled on the API-to-gateway request.

### Review conclusion

**Pass.** No new caller-controlled network destination is introduced.

---

## 3. Threat: BYOK credential exposure

### Risk

The provider API key is the most sensitive data used by this endpoint. It could leak through:

- PostgreSQL;
- browser/API responses;
- logs;
- exception strings;
- query parameters;
- traces;
- provider-health metadata;
- test fixtures or live CI traffic.

### Control implemented

The API key is not accepted from the connectivity-test request. It is resolved from the stored `secret_ref` through the existing tenant secret-store boundary.

The key crosses the API-to-gateway service boundary only in the authenticated private JSON request required to invoke the provider adapter. It is not included in a URL or query string.

The public result contains only:

- provider status;
- normalized stable error code or null.

The implementation does not write plaintext credentials into PostgreSQL. `last_error_code` receives only an approved normalized code.

The LLM-Gateway request uses Pydantic `SecretStr` for the credential and never returns the private request object.

No live provider credentials are used by CI tests. Provider calls are represented by fake adapters/fake gateway clients.

### Verification

Tests assert that:

- the public response does not contain the fake API key;
- the encrypted local secret-store file does not contain the plaintext test key;
- captured test logs do not contain the fake key;
- private gateway responses do not include generated content or provider request IDs;
- raw HTTP failure text containing a fake key is normalized to `PROVIDER_UNAVAILABLE` without returning that text.

### Residual deployment requirement

Production traffic between the API and LLM Gateway must use the platform's protected service network/TLS configuration, because the private request necessarily carries the plaintext provider credential in memory/on the encrypted service channel.

### Review conclusion

**Pass with existing platform transport requirement.** The implementation does not create a new persistent or browser-visible secret path.

---

## 4. Threat: unauthorized tenant/user can test a connection

### Risk

A user without provider-management rights could consume tenant provider quota or use a provider ID from another tenant to discover configuration.

### Control implemented

The route reuses the existing provider-management permission:

```text
ai.providers.manage
```

The first service operation resolves active membership and then performs a provider lookup scoped by both:

- current tenant ID;
- provider connection ID.

A provider belonging to another tenant follows the same non-disclosing `PROVIDER_NOT_FOUND` behavior as a nonexistent provider ID.

The credential is not resolved until after tenant/permission checks succeed.

### Verification

Real PostgreSQL integration tests cover:

- same-tenant user without `ai.providers.manage` -> `403 FORBIDDEN` with no provider call;
- different-tenant provider ID -> `404 PROVIDER_NOT_FOUND` with no cross-tenant disclosure.

### Review conclusion

**Pass.** Existing tenant/RBAC boundaries are preserved.

---

## 5. Threat: abuse and cost amplification through repeated tests

### Risk

Even a tiny provider request consumes upstream capacity. A user could repeatedly call the endpoint, and a process-local limiter would be ineffective when Serviq runs multiple API workers or replicas.

### Control implemented

The implementation preserves the frozen limits:

```text
provider.test.user       = 10 / minute
provider.test.connection = 30 / hour
```

Production enforcement uses shared Valkey state.

The keys include tenant ID and the limiting subject, not provider credentials.

A single atomic Valkey script:

1. reads both counters;
2. rejects if either frozen limit is already exhausted;
3. otherwise increments both counters and creates the appropriate expiry windows;
4. returns a retry-after value when blocked.

This avoids a race where two API workers separately check an old count and both allow the request.

The limiter runs before secret resolution and before the provider call.

If Valkey is unavailable or returns malformed data, the endpoint fails closed with `PROVIDER_TEST_UNAVAILABLE`; it does not silently bypass abuse controls.

### Verification

Unit tests verify:

- exact 10, 30, 60-second, and 3,600-second values passed into one atomic eval call;
- tenant/user/connection scoping of keys;
- a limit rejection exposes a safe retry-after value;
- Valkey connection failure becomes a safe unavailable error;
- malformed Valkey results fail closed;
- no secret appears in limiter keys.

API integration tests also prove a denied limiter prevents gateway invocation.

### Dependency review

OPE-298 adds the official Valkey Python client to the API dependency set. The generated lock resolved `valkey==6.1.1` in the repository CI environment. The API dependency remains covered by the repository's existing pip-audit security workflow.

### Review conclusion

**Pass.** Abuse control remains effective across horizontally scaled API processes and fails safely.

---

## 6. Threat: provider outage falsely marks a credential invalid

### Risk

A timeout, 429, or provider outage is not proof that a tenant API key is wrong. Persisting every failure as `invalid` would create false health state and could disable later routing.

### Control implemented

Only the normalized authentication failure:

```text
PROVIDER_AUTH_FAILED
```

moves an enabled connection to `invalid`.

The following failures preserve the current status while recording the latest attempt time and safe code:

- `PROVIDER_RATE_LIMITED`;
- `PROVIDER_TIMEOUT`;
- `PROVIDER_UNAVAILABLE`;
- `PROVIDER_INVALID_REQUEST`.

`PROVIDER_INVALID_REQUEST` also preserves status because the health-check model and prompt are Serviq-owned; a provider-side rejection could represent an outdated server-owned test model rather than a bad tenant credential.

### Verification

PostgreSQL integration coverage starts a provider at `active` and proves each transient/configuration error keeps it active while updating `last_tested_at` and `last_error_code`.

### Review conclusion

**Pass.** Persisted trust metadata distinguishes credential evidence from provider/service health.

---

## 7. Threat: stale in-flight test overwrites a rotated credential

### Risk

Consider this race:

1. old key A begins a test;
2. an administrator rotates the provider to key B;
3. test A succeeds;
4. naive code writes `active` onto the provider row.

The UI would now show key B as active even though key B was never tested.

### Control implemented

OPE-298 intentionally does not keep a database transaction open during the provider call.

Instead it uses two short transactions:

**Transaction 1**

- authorize;
- tenant-scope the provider row;
- capture provider enum and `secret_ref`.

**No database transaction**

- rate-limit;
- resolve the captured secret;
- call LLM Gateway/provider.

**Transaction 2**

- lock the provider row;
- verify the current `secret_ref` and provider still match the captured values;
- persist the result only when they match.

If they differ, the test result is rejected as `PROVIDER_TEST_STALE`.

### Verification

A real PostgreSQL integration test rotates the key in a separate database session while the fake gateway call is in flight. The API returns `409 PROVIDER_TEST_STALE`, and the new key remains `untested` with no inherited timestamp/error.

### Review conclusion

**Pass.** Old credential results cannot stamp trust onto replacement credentials.

---

## 8. Threat: database lock/transaction held during external provider call

### Risk

Holding a PostgreSQL transaction or row lock while waiting on an external model provider can cause:

- long lock durations;
- blocked admin updates;
- exhausted database connections;
- cascading latency under provider outages;
- harder retry/concurrency behavior.

### Control implemented

The provider/gateway network call occurs between two explicit database transactions. No external call is awaited while either transaction is open.

The second transaction locks only for the short validation/persistence step.

### Review conclusion

**Pass.** External provider latency is not converted into database lock latency.

---

## 9. Threat: provider/raw HTTP errors leak into metadata or browser responses

### Risk

Provider error bodies can contain request fragments, account information, internal IDs, or provider-specific details. Persisting raw bodies also creates an unbounded data and privacy problem.

### Control implemented

The LLM adapters already normalize provider failures to the C-4 error vocabulary.

The private gateway returns only:

- `ok`;
- normalized `errorCode`.

The API-to-gateway HTTP client treats malformed/non-200 internal responses as `PROVIDER_UNAVAILABLE` and does not include response text in its result.

Provider metadata stores only the stable code.

Public error messages are fixed Serviq-owned strings.

### Verification

A unit test makes the internal HTTP transport return a `500` body containing both a fake raw provider message and a fake credential. The resulting object contains only `PROVIDER_UNAVAILABLE`.

Integration tests verify database error fields contain normalized codes only.

### Review conclusion

**Pass.** Raw provider/internal HTTP bodies are not propagated into the public or persistence contracts.

---

## 10. Threat: hidden retries multiply cost or hide a failing connection

### Risk

A connectivity test should report the observed condition. Automatic retries can:

- turn one admin action into several paid provider calls;
- make rate limiting inaccurate;
- hide intermittent connectivity problems;
- exceed the intended timeout.

### Control implemented

OPE-298 itself makes one gateway request and does not retry.

The private gateway invokes the selected provider adapter once. Provider adapters retain the retry behavior already frozen by their respective ADRs; OPE-298 does not add a retry layer.

The API-to-gateway client does not retry a timeout or HTTP failure.

### Verification

The HTTP timeout unit test counts transport calls and verifies exactly one request is attempted.

### Review conclusion

**Pass.** OPE-298 adds no hidden retry/cost multiplier.

---

## 11. Threat: disabled connection is accidentally reactivated

### Risk

A manual/administrative `disabled` state should not be changed merely because a health test was requested or completed concurrently.

### Control implemented

If a connection is already disabled during the initial read, the endpoint returns safe disabled state without rate limiting, secret resolution, or provider invocation.

If it becomes disabled while an external test is in flight, the locked second-phase write does not reactivate it.

### Verification

Integration tests prove a disabled provider produces no limiter call and no gateway call.

### Review conclusion

**Pass.** Connectivity testing respects the existing disabled state.

---

## 12. Private gateway authentication

### Risk

If the private route were anonymously callable, an internal network actor could send arbitrary provider credentials into provider adapters or consume capacity.

### Control implemented

The private route requires:

```text
Authorization: Bearer <LLM_GATEWAY_INTERNAL_TOKEN>
```

The expected token comes from platform configuration, not the request.

Comparison uses `hmac.compare_digest` rather than ordinary string equality.

If the expected internal token is not configured, the gateway fails closed with a safe unavailable response rather than allowing unauthenticated access.

### Verification

Gateway route tests prove missing internal auth returns `401` before adapter invocation.

### Review conclusion

**Pass**, subject to normal production service-network/TLS enforcement.

---

## 13. Observability and logging review

### Safe fields

OPE-298 can safely observe categorical or nonsecret identifiers such as:

- tenant ID;
- provider connection ID;
- provider enum;
- correlation ID;
- normalized result code;
- duration.

### Fields that must remain excluded

- plaintext API key;
- secret-store plaintext;
- provider response body;
- generated model content;
- internal bearer token;
- raw SDK exception text;
- private request body.

The current implementation does not add structured logging of those sensitive values.

### Review conclusion

**Pass for OPE-298.** Future observability work must preserve the same redaction boundary.

---

## 14. CI and live-network review

### Risk

Tests that call live OpenAI/Anthropic/Gemini/OpenRouter APIs would require real credentials, incur cost, become flaky, and risk leaking secrets into CI logs.

### Control implemented

OPE-298 provider tests are deterministic:

- LLM-Gateway adapter calls use fake adapters;
- API route integration uses a fake gateway;
- API-to-gateway transport uses `httpx.MockTransport`;
- rate-limit logic uses a fake eval client;
- database lifecycle uses the repository's real PostgreSQL integration service;
- no live model-provider request is required.

### Review conclusion

**Pass.** The CI coverage is meaningful without external provider credentials.

---

## 15. Dependency and supply-chain review

OPE-298 introduces one API runtime dependency:

```text
valkey>=6.1,<7
```

The repository lock refresh resolves it deterministically for CI, and the existing Security workflow audits API Python dependencies with `pip-audit`.

No new LLM-provider SDK is introduced by this ticket. Existing adapters and their approved dependencies are reused.

### Review conclusion

**Pass after final Security workflow succeeds on the merge head.**

---

## 16. Remaining risks intentionally outside OPE-298

These are not defects in this ticket but are important future operational concerns:

1. **Periodic provider monitoring** — OPE-298 is user-triggered; it is not a background uptime monitor.
2. **Test-model lifecycle ownership** — provider model identifiers can change. ADR-014 makes the mapping architecture-owned; future model retirement requires an explicit mapping update and regression tests.
3. **Production service TLS/network policy** — deployment must secure the private API-to-gateway hop.
4. **Valkey high availability** — OPE-298 correctly fails closed when Valkey is unavailable, but platform HA determines how often administrators see that safe failure.
5. **General agent gateway routing** — this private health path is intentionally not the general C-4 HTTP routing solution.
6. **Model configuration CRUD/reference semantics** — handled separately by OPE-299 and its architecture decisions.

None of these should be silently folded into this health-check endpoint.

---

## Final security checklist

- [x] Public route does not accept arbitrary model/prompt/body.
- [x] Private schema rejects extra generation controls.
- [x] No caller-controlled upstream URL.
- [x] Tenant scoping enforced.
- [x] `ai.providers.manage` required.
- [x] BYOK credential resolved through tenant secret store.
- [x] Credential not persisted in PostgreSQL or returned publicly.
- [x] Private gateway bearer authentication required.
- [x] Constant-time internal token comparison.
- [x] Fixed minimal provider request.
- [x] 4-token output cap.
- [x] 5-second provider timeout.
- [x] No OPE-298 retry loop.
- [x] Shared Valkey rate limits.
- [x] Both frozen limits consumed atomically.
- [x] Rate-limit dependency fails closed.
- [x] External provider call outside DB transaction.
- [x] Credential-rotation stale-result guard.
- [x] Authentication failure is distinguished from transient failures.
- [x] Disabled connections are not invoked.
- [x] Raw provider/internal HTTP bodies are not propagated.
- [x] CI uses mocks/fakes rather than live provider credentials.
- [x] New dependency included in frozen API lock.
- [ ] Final PR CI green on final review head.
- [ ] Final PR Security green on final review head.

The final two boxes are intentionally left open until the exact final PR head passes both repository workflows. They must be marked complete before merge/closure.
