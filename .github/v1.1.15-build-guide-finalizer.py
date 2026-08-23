from __future__ import annotations

from pathlib import Path

GUIDE_MARKER = "# V1.1.15 — Live Keycloak workforce OIDC integration coverage"
CI_START = "# V1.1.15 TEMP BUILD GUIDE FINALIZER START\n"
CI_END = "# V1.1.15 TEMP BUILD GUIDE FINALIZER END\n"

section = r'''

---

# V1.1.15 — Live Keycloak workforce OIDC integration coverage

**GitHub issue:** #175  
**Linear ticket:** OPE-307  
**Implementation branch:** `v1.1.15`

## Why this ticket exists

Serviq already had two important workforce-authentication foundations before V1.1.15. OPE-265 provided a pinned local Keycloak service, and OPE-280 implemented cryptographic OIDC token validation with deterministic unit tests. Those tests prove the validator logic in isolation, but they do not prove that the actual Keycloak configuration used by local development can issue a token whose discovery metadata, signing keys, issuer, audience, and subject all match the validator's real expectations.

V1.1.15 closes that evidence gap. It adds a deterministic test-only Keycloak realm/client fixture and a dedicated CI integration job that starts the real pinned Keycloak container, imports the fixture, obtains a real workforce token, and validates that token through the existing `WorkforceOidcValidator` without changing the production validator contract.

## What did not change

This ticket does not change the public OIDC claims contract, customer identity, platform-console authentication, tenant membership ownership, permission ownership, database schema, or production identity-provider configuration. `services/api/app/core/auth.py` remains behaviorally unchanged.

`infra/docker/compose.yml` also remains unchanged. The ordinary local Keycloak service therefore does not suddenly gain permanent test users or a preconfigured Serviq realm. The dedicated integration harness reuses the existing Compose service definition and mounts the test fixture only into a one-off container started for this test.

## The deterministic test realm

The fixture lives at:

```text
infra/keycloak/serviq-test-realm.json
```

It defines the enabled test realm `serviq` and one non-production public client, `serviq-test`.

The client has direct-access grants enabled only so a non-interactive integration test can obtain a token without implementing or automating a browser login flow. The client has no production secret and no service account. An explicit OIDC audience mapper places `serviq-test` in access-token audience claims so the token exercises the same exact-audience validation that production workforce tokens must satisfy.

The fixture contains one enabled deterministic workforce user and one disabled deterministic workforce user. Their passwords are obvious placeholder strings committed only for the disposable test realm. They are not credentials for any production or shared identity system.

The enabled user's fixed subject UUID makes the success assertion deterministic. The disabled user exists specifically to prove that Keycloak refuses token issuance for a disabled subject.

## Why direct-access grants are acceptable only here

Serviq's workforce browser architecture remains Authorization Code + PKCE with server-managed session state. V1.1.15 does not replace that design with a password grant.

The direct-access grant is limited to the imported test client because CI needs a deterministic way to obtain a signed token without adding a browser, callback server, session implementation, or real user credentials to an infrastructure integration test. Product login code must not copy this test-only grant pattern.

## The live integration test

The test module is:

```text
services/api/tests/integration/test_keycloak_oidc_integration.py
```

It is skipped unless this explicit opt-in flag is present:

```text
SERVIQ_KEYCLOAK_OIDC_INTEGRATION=1
```

This keeps the normal unit suite fast and prevents a developer from accidentally depending on a running identity provider for every test command.

When enabled, the test obtains an access token from the real local Keycloak token endpoint with a five-second HTTP timeout and redirects disabled. The helper never prints the returned token.

The success path then gives that token to the existing `WorkforceOidcValidator`. The validator performs its normal discovery request, reads the real Keycloak JWKS, verifies the RS256 signature, requires the exact configured issuer and audience, validates temporal claims, and requires a non-empty subject.

The test verifies the normalized identity contains the expected issuer and deterministic subject. It also asserts that `tenant_id` and `permissions` are not fields on the trusted workforce identity DTO. A correctly signed identity token still cannot become a source of Serviq tenant authorization.

## Wrong-audience proof

The integration test takes the real Keycloak-issued token and runs the real validator with a deliberately incorrect configured audience.

The result must be Serviq's stable `UNAUTHENTICATED` category and the generic message `Authentication failed.`

The test does not disable signature verification or fabricate a locally signed token. Discovery and JWKS still come from the real Keycloak instance. Only the expected audience is wrong, which proves the existing trust boundary fails closed against a real IdP-issued token.

## Wrong-issuer proof

The wrong-issuer case also keeps the real Keycloak token and real Keycloak discovery/JWKS path. The test injects an `OidcMetadataCache` that loads metadata and signing keys from the real `localhost` issuer while configuring the validator to expect the alternate loopback issuer `127.0.0.1`.

This separates two questions cleanly: the token is genuinely signed by the live Keycloak key, but its `iss` claim is not the issuer the validator was configured to trust. Validation must fail with the same safe unauthenticated result.

Using the real metadata cache makes this test deterministic and avoids depending on whether Keycloak itself canonicalizes two loopback hostnames the same way.

## Disabled and unknown users

The integration test requests tokens for the disabled fixture user and for a username that does not exist.

Both requests must return HTTP 401 with Keycloak's `invalid_grant` category and without an access or refresh token. This proves the real test realm does not issue a usable workforce identity for these subjects.

A different boundary handles a Serviq internal user who becomes disabled after external identity verification. OPE-281 already owns that database-backed user-status behavior. V1.1.15 does not duplicate it inside the cryptographic token validator.

## Token-redaction proof

The test captures Python logs while deliberately causing an audience-validation failure. It then asserts that the complete raw access token is absent from both captured logs and the safe `AuthenticationError` string.

The dedicated CI readiness failure path is also designed not to dump credentials blindly. It limits diagnostics to container state plus the last bounded container log lines, then redacts fields shaped like access tokens, refresh tokens, ID tokens, client secrets, passwords, and three-part JWT strings before printing them.

No token is uploaded as an artifact, stored in the database, copied to a snapshot, or returned from the test helper.

## How CI starts the real Keycloak service

The permanent CI job is `keycloak-oidc-integration`. It keeps the workflow's existing repository-level `contents: read` permission and uses the same immutable GitHub Action SHAs as the other jobs.

The job installs the frozen API environment, then reuses the existing Compose `keycloak` service with a one-off command conceptually equivalent to:

```text
docker compose -f infra/docker/compose.yml run \
  --detach \
  --name serviq-keycloak-oidc \
  --service-ports \
  --no-deps \
  --volume "$PWD/infra/keycloak/serviq-test-realm.json:/opt/keycloak/data/import/serviq-test-realm.json:ro" \
  keycloak start-dev --import-realm
```

This means the test uses the exact Keycloak image, environment contract, and local ports owned by Compose, but the deterministic realm exists only for the integration container.

## Readiness and safe diagnostics

CI waits for two independent signals:

```text
http://localhost:9000/health/ready
http://localhost:8080/realms/serviq/.well-known/openid-configuration
```

The first proves the Keycloak process is ready. The second proves the test realm was imported and its OIDC discovery endpoint is reachable.

The wait is bounded. If readiness does not arrive, the job fails instead of hanging indefinitely. It prints bounded, redacted container diagnostics so an operator can distinguish startup failure from test failure without exposing tokens or secrets.

## Cleanup always runs

The final CI cleanup step uses `if: always()`. It force-removes the named one-off Keycloak container when necessary and runs Compose teardown with volumes/orphans cleanup. Cleanup therefore executes after success, assertion failure, or readiness failure.

This matters on shared CI runners because a failed authentication integration should not leave an identity-provider container or test state behind for later steps.

## Local manual execution

A developer with Docker, Python 3.14, uv, and the normal Serviq prerequisites can reproduce the integration path without changing the ordinary local stack.

From the repository root, set the same safe test environment used by CI, including:

```text
SERVIQ_KEYCLOAK_OIDC_INTEGRATION=1
SERVIQ_ENV=test
OIDC_ISSUER_URL=http://localhost:8080/realms/serviq
OIDC_CLIENT_ID=serviq-test
KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD=test-placeholder
```

Start the one-off Keycloak container with the fixture mounted and `start-dev --import-realm`, wait for the management readiness endpoint and realm discovery endpoint, then run:

```text
cd services/api
uv sync --frozen
uv run pytest tests/integration/test_keycloak_oidc_integration.py
```

After the test, remove the named container and run the same Compose teardown used by CI.

Do not copy the test user's placeholder password, direct-access grant, or test realm into production configuration.

## Main files changed

```text
infra/keycloak/serviq-test-realm.json
services/api/tests/integration/test_keycloak_oidc_integration.py
.github/workflows/ci.yml
docs/repo_context.md
docs/SERVIQ_BUILD_GUIDE.md
```

`infra/docker/compose.yml`, the production validator implementation, database schema, public OIDC contract, customer identity, and platform-console authentication remain unchanged.

## What this improves

Before V1.1.15, Serviq could say the validator was strongly unit-tested and that Keycloak could start, but those were two separate pieces of evidence. After this ticket, CI proves those pieces interoperate through a real signed token and real discovery/JWKS exchange.

That catches a class of integration mistakes unit tests cannot detect, such as a realm issuer mismatch, missing audience mapper, client identifier drift, broken realm import, or Keycloak version/configuration incompatibility.

The negative cases also demonstrate that the real integration remains fail-closed. A valid signature is not enough when audience or issuer is wrong, and a disabled or unknown test subject cannot obtain a token.

## What V1.1.15 intentionally does not add

This ticket does not implement browser login automation, Authorization Code + PKCE UI wiring, production IdP configuration, customer authentication, platform-console authentication, tenant selection or membership lookup, new OIDC claims, persistent test credentials outside the fixture, production secrets, a second auth framework, or changes to `WorkforceOidcValidator` behavior.

Those remain separate trust boundaries and product/architecture responsibilities.

## Completion rule

V1.1.15 is complete only when the deterministic fixture, live integration tests, dedicated CI job, repository context, and this cumulative Build Guide update are present on the final branch; the existing auth unit suite and the real Keycloak integration job pass on the exact pull-request head; the final diff contains no token or production secret; cleanup is proven to run unconditionally; and the validated pull request is merged to `main`.

GitHub issue #175 and Linear OPE-307 close only after that merged evidence is recorded. Documentation does not substitute for a green real-integration job.
'''

guide = Path("docs/SERVIQ_BUILD_GUIDE.md")
text = guide.read_text(encoding="utf-8")
if GUIDE_MARKER not in text:
    guide.write_text(text.rstrip() + section + "\n", encoding="utf-8")

ci = Path(".github/workflows/ci.yml")
ci_text = ci.read_text(encoding="utf-8")
if CI_START not in ci_text or CI_END not in ci_text:
    raise SystemExit("temporary CI finalizer markers are missing")
before, remainder = ci_text.split(CI_START, 1)
_, after = remainder.split(CI_END, 1)
ci.write_text(before.rstrip() + "\n" + after.lstrip(), encoding="utf-8")

Path(".github/workflows/v1.1.15-build-guide-finalizer.yml").unlink(missing_ok=True)
Path(".github/v1.1.15-build-guide-finalizer.py").unlink(missing_ok=True)
