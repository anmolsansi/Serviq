# OPE-280 Security Review — Workforce OIDC Token Validation

## Review status

Approved for merge only after the repository CI and Security workflows pass on the final pull-request head.

## Trust boundary reviewed

The input is an untrusted bearer token. The output is a small `VerifiedWorkforceIdentity` object that downstream code may trust for identity mapping. Tenant membership and authorization are intentionally not part of this boundary.

## Threats reviewed

### Signature bypass

Mitigation: the validator delegates JWT cryptography to `joserfc`, supplies the issuer JWKS as the verification key set, and passes an explicit `RS256` algorithm allowlist. Signature verification is never disabled.

### `alg=none` or algorithm confusion

Mitigation: only `RS256` is accepted. The validator does not use an algorithm name from token claims to expand the allowlist.

### Issuer confusion

Mitigation: discovery is always derived from the configured `OIDC_ISSUER_URL`, never from an untrusted token claim. Discovery metadata must repeat the exact configured issuer. The JWT `iss` claim must also equal that exact issuer.

### Audience confusion

Mitigation: `aud` is required and must match the configured `OIDC_CLIENT_ID` exactly.

### Expired or incomplete identities

Mitigation: `exp` and `sub` are essential claims. The claims registry validates expiration, and Serviq separately rejects blank subjects.

### Tenant/permission injection through JWT custom claims

Mitigation: the trusted identity DTO has no tenant or permission fields. Arbitrary JWT claims are not copied into it. Tenant membership and capabilities remain database-derived in later tickets.

### JWKS SSRF / metadata redirection

Mitigation: discovery URL comes only from the configured issuer. The HTTP client does not follow redirects. Staging/production require HTTPS. Local/test permit HTTP only on loopback hosts. Discovery-provided `jwks_uri` is subjected to the same URL policy before any request is made.

### Authentication dependency amplification

Mitigation: discovery and JWKS are cached for at most five minutes and guarded by a single async lock. Concurrent cold-cache requests do not each fetch metadata independently.

### Oversized metadata response

Mitigation: OIDC JSON responses are bounded to one megabyte before JSON parsing.

### Token leakage

Mitigation: raw tokens are never logged, persisted, placed in exceptions, returned in DTOs, or copied into error messages. All validation/network/JOSE failures become the stable `AuthenticationError` category with the generic message `Authentication failed.`

### Library exception leakage

Mitigation: JOSE claim/signature failures, malformed token failures, network failures, invalid metadata, and key-set import failures are normalized at the auth boundary. Raw provider/library text does not escape.

## Test coverage required by this review

- correct issuer/audience/signature/expiry/subject succeeds;
- wrong issuer fails;
- wrong audience fails;
- expired token fails;
- invalid signature fails;
- missing subject fails;
- blank subject fails;
- malformed token fails safely;
- discovery issuer mismatch fails;
- metadata/JWKS fetches are cached;
- token-supplied tenant/permission claims do not enter the trusted DTO;
- raw token does not appear in errors or captured logs.

## Deliberate non-goals

This review does not approve browser authorization-code/PKCE handling, session-cookie construction, membership lookup, RequestContext population, invitation email matching, or platform-operator authentication. Those remain separate trust boundaries and require their own tickets/reviews.

## Residual risk

A signing-key rotation may cause validation failures until the bounded cache expires. OPE-280 intentionally avoids an attacker-triggerable refresh-on-every-invalid-signature path. If production operational requirements later demand faster rotation, add a bounded background/issuer-driven refresh policy rather than fetching JWKS for every failed token.
