from pathlib import Path


focused = Path("docs/OPE_279_285_IMPLEMENTATION_GUIDE.md")
focused_marker = "# OPE-280 — Implement workforce OIDC token validation"
focused_section = r'''

---

# OPE-280 — Implement workforce OIDC token validation

## What problem this ticket solves

A JWT is only a signed container of claims. Serviq must not treat the text inside a workforce token as trusted simply because the token looks structurally correct. Before identity data is allowed into later user/membership code, Serviq must prove that the configured identity provider signed the token, that the token was meant for Serviq, that it has not expired, and that it identifies a real subject.

OPE-280 creates that cryptographic trust boundary.

## Architecture decision made before coding

The ticket contained an explicit stop condition because the API scaffold did not have an approved JOSE/JWT library. Instead of writing token cryptography by hand or quietly adding a framework, OPE-280 records ADR-003.

ADR-003 freezes these V1 choices:

- `joserfc` performs JWT/JWK verification;
- the already-used `httpx` client becomes a runtime dependency for OIDC discovery/JWKS retrieval;
- only `RS256` workforce signatures are accepted;
- issuer discovery and JWKS are cached for at most five minutes;
- staging/production metadata must use HTTPS;
- local/test HTTP is allowed only for loopback development hosts.

The dependency lockfile was regenerated after the architecture decision, so CI installs the exact resolved dependency graph instead of resolving a different set on every machine.

## Stable authentication failure

`services/api/app/core/errors.py` now includes `AuthenticationError` with stable code `UNAUTHENTICATED` and the generic message `Authentication failed.`

The reason for a generic boundary error is security. A caller should not receive raw JOSE messages that reveal whether a key ID was found, how a signature failed, or which internal metadata request errored. Detailed provider/library text can also accidentally contain untrusted token fragments.

## Verified identity DTO

`VerifiedWorkforceIdentity` is deliberately small. It contains only:

- exact configured issuer;
- verified subject;
- normalized email when present;
- strict email-verification boolean;
- optional display name derived from `name` or `preferred_username`.

It does **not** contain arbitrary token claims. In particular, token-supplied tenant IDs and permissions are ignored even if present in a correctly signed token. Serviq's tenant membership and capabilities must come from its own database in OPE-282.

## Discovery and JWKS cache

`OidcMetadataCache` starts from the configured issuer. It builds the standard discovery URL itself instead of reading an issuer URL from the token.

On a cold cache it:

1. fetches discovery metadata;
2. verifies discovery repeats the exact configured issuer;
3. extracts `jwks_uri`;
4. validates the metadata URL policy;
5. fetches the public key set;
6. imports the JWKS into a typed `KeySet`;
7. stores it for a bounded five-minute lifetime.

An async lock makes this single-flight. If many requests arrive at the same moment while the cache is empty, one refresh runs and the others reuse the result.

The HTTP fetch path uses a five-second timeout, does not follow redirects, and rejects OIDC JSON responses larger than one megabyte.

## Token validation sequence

`WorkforceOidcValidator.validate()` performs the following sequence:

1. reject blank input;
2. obtain the trusted issuer key set from the bounded cache;
3. cryptographically decode/verify using only `RS256`;
4. require exact configured `iss`;
5. require exact configured `aud`;
6. require and validate `exp`;
7. require `sub`;
8. separately reject a blank subject;
9. normalize only the approved identity profile fields;
10. return the frozen verified identity DTO.

Any metadata, network, JOSE, signature, claims, or malformed-token failure becomes `AuthenticationError` without returning the raw dependency exception.

## Email handling

Email is profile data, not the primary identity key. If a string email claim exists, it is trimmed and case-folded. `email_verified` is true only when the claim is literally boolean `true`.

An unverified email can therefore be carried as profile information while remaining explicitly unverified. Later invitation acceptance code must not treat an unverified email as proof that the user owns an invitation address.

## Tests added

`services/api/tests/test_workforce_oidc.py` uses locally generated deterministic-purpose RSA/JWK fixtures and a fake discovery/JWKS fetcher. No external identity provider is needed for automated tests.

Coverage includes:

- valid token success;
- exact normalized identity output;
- proof that token tenant/permission claims are discarded;
- wrong issuer;
- wrong audience;
- expired token;
- missing subject;
- blank subject;
- invalid signature;
- malformed token;
- discovery issuer mismatch;
- two validations within cache lifetime producing only one discovery + one JWKS fetch;
- unverified email behavior;
- raw token absent from error text and captured logs.

## Security review

`docs/security-reviews/OPE-280-workforce-oidc-validation.md` records the explicit security review for this trust boundary. It covers signature bypass, algorithm confusion, issuer/audience confusion, token claim injection, metadata SSRF/redirect behavior, oversized metadata, dependency amplification, token leakage, and residual key-rotation risk.

The final PR must still pass the permanent OPE-272 security workflow before merge. The review document is not a substitute for CodeQL, Gitleaks, Trivy, and dependency auditing.

## What this improves

After OPE-280, downstream code can ask one component to validate a workforce JWT and receive either a small verified identity or one safe authentication failure. No later service needs to parse JWT claims independently, choose its own algorithm policy, fetch JWKS on every request, or risk copying tenant/permission claims from the identity provider into Serviq authorization.

## What remains

OPE-280 does not create browser sessions, persist users, resolve memberships, construct RequestContext, or expose login routes. OPE-281 consumes the verified identity DTO to create/reuse Serviq's internal user identity. OPE-282 then resolves tenant membership and capabilities from PostgreSQL.
'''

focused_text = focused.read_text()
if focused_marker not in focused_text:
    focused.write_text(focused_text + focused_section)

build = Path("docs/SERVIQ_BUILD_GUIDE.md")
build_marker = "# OPE-280 — workforce OIDC token validation"
build_section = r'''

---

# OPE-280 — workforce OIDC token validation

OPE-280 adds Serviq's first real cryptographic workforce identity-verification boundary. A workforce JWT is not trusted because it contains familiar-looking fields. The API now verifies the signature against the configured issuer's JWKS, allows only RS256, requires exact issuer and audience, validates expiry, and requires a non-empty subject before identity data is considered trusted.

The API scaffold did not previously contain an approved JOSE/JWT package, so the ticket's architecture stop condition was triggered. ADR-003 resolves that deliberately by approving `joserfc` and moving the already-used `httpx` client into runtime dependencies for OIDC metadata retrieval. The dependency lockfile was regenerated so every environment installs the same resolved packages.

OIDC discovery always starts from configured `OIDC_ISSUER_URL`, never from an issuer supplied by the token. Discovery must repeat that exact issuer. Its `jwks_uri` is then validated before fetching. Production/staging metadata must use HTTPS, while local/test HTTP is limited to loopback development hosts. Redirects are disabled, requests have a five-second timeout, and metadata bodies are bounded.

Discovery and JWKS are cached for at most five minutes under one async lock. This prevents authentication from performing two identity-provider network requests for every API request and prevents a cold-cache burst from starting many identical refreshes.

Successful validation returns only `VerifiedWorkforceIdentity`: issuer, subject, optional normalized email, email verification state, and optional display name. Even a valid signed token cannot inject a Serviq tenant ID or permission list because those fields are not copied into the trusted DTO. Tenant membership and authorization remain database-owned.

All failures become the stable internal `UNAUTHENTICATED` category with the generic message `Authentication failed.` Raw token text and raw JOSE/network exceptions are not logged, stored, or returned.

Automated tests cover success plus wrong issuer, wrong audience, expiry, invalid signature, missing/blank subject, malformed token, discovery mismatch, caching, email verification behavior, claim filtering, and token redaction. A dedicated security review is recorded at `docs/security-reviews/OPE-280-workforce-oidc-validation.md`.

This ticket does not implement browser PKCE/session handling, user persistence, membership lookup, tenant resolution, or RequestContext construction. Those remain separate trust boundaries in later tickets.

The detailed implementation narrative for OPE-280 is in `docs/OPE_279_285_IMPLEMENTATION_GUIDE.md`.
'''

build_text = build.read_text()
if build_marker not in build_text:
    build.write_text(build_text + build_section)
