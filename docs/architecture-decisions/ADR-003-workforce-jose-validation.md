# ADR-003 — Workforce JOSE validation library and algorithm policy

## Status

Accepted for OPE-280.

## Context

OPE-280 requires server-side validation of workforce OIDC JWTs, but the API scaffold did not contain an approved JOSE/JWT dependency. The ticket explicitly says to stop rather than hand-roll token verification or silently add an auth framework.

Serviq already freezes the identity provider boundary as OIDC/Keycloak, the workforce audience as `OIDC_CLIENT_ID`, and the issuer as `OIDC_ISSUER_URL`. The remaining missing decision is which focused JOSE implementation performs cryptographic JWT verification and which signing algorithms Serviq accepts for V1.

The security rules also prohibit hand-written JWT cryptography and require fail-closed signature, issuer, audience, expiry, and subject checks.

## Decision

1. Use `joserfc` as the API's focused JOSE/JWT implementation.
2. Pin the API dependency to the `1.7.x` release line through `pyproject.toml` plus `uv.lock`.
3. Use `httpx` as a runtime dependency for OIDC discovery/JWKS retrieval. It was already present in the API development dependency set, so this promotes an existing approved HTTP client rather than adding a second HTTP stack.
4. Accept only `RS256` for V1 workforce JWT signature verification.
5. Never infer an algorithm from untrusted token content and never allow `none`.
6. Import issuer JWKS as a typed key set and let `kid` select the matching public key.
7. Validate exact configured issuer, exact configured audience, required expiry, and required non-empty subject after cryptographic verification.
8. Treat discovery/JWKS metadata as process-local cached configuration with a five-minute maximum lifetime. Cache access is single-flight under an async lock so bursts do not cause one network request per API request.
9. Require HTTPS discovery/JWKS URLs in staging/production. Local/test may use loopback HTTP for the repository's Keycloak development profile.
10. Normalize every JOSE, claim, metadata, timeout, or network failure into Serviq's stable internal authentication error. Raw library error text and raw tokens must not escape the boundary.

## Why `joserfc`

The Authlib project split its JOSE implementation into `joserfc` and recommends it for current JOSE/JWT work. It provides typed JWK/KeySet handling, explicit allowed-algorithm controls, and a claims registry rather than requiring Serviq to implement JWT primitives itself.

## Why only RS256

An allowlist is safer than accepting every algorithm a library supports. Serviq's V1 local identity provider is Keycloak and the project does not currently require multiple JWT signing algorithms. Freezing one asymmetric algorithm prevents algorithm-downgrade/confusion behavior and keeps the security surface small. Supporting another algorithm later requires an explicit ADR update and tests.

## Consequences

### Positive

- JWT cryptography is delegated to a maintained JOSE implementation.
- `alg=none` and non-RS256 tokens fail before claims become trusted.
- The validator has one predictable key type and algorithm path.
- Key rotation can be handled by JWKS `kid` plus bounded metadata refresh.
- OIDC metadata is not fetched on every request.

### Tradeoffs

- A deployment whose workforce issuer is configured for a different signing algorithm must either configure RS256 or approve an ADR change before use.
- The process-local cache is intentionally simple. Multi-process instances may each refresh metadata once per cache lifetime.
- This ADR validates tokens only. Browser authorization-code/PKCE and session-cookie lifecycle remain separate architecture work.

## Rejected alternatives

### Hand-written JWT verification

Rejected because it violates the security/tech-stack rule against hand-rolled JWT cryptography.

### Deprecated `authlib.jose`

Rejected because current Authlib documentation directs new JOSE work to `joserfc`.

### Accept every recommended JOSE algorithm

Rejected because Serviq has no V1 requirement for algorithm agility and an unnecessary broad allowlist increases the verification surface.

### Fetch JWKS on every request

Rejected because it makes authentication availability and latency depend on an external metadata round-trip for every API call and can amplify an issuer outage.
