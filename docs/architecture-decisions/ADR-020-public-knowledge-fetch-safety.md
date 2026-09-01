# ADR-020 — Public knowledge fetch safety boundary

## Status

Accepted for V1.3.05 / OPE-311.

## Date

2026-09-01

## Context

Serviq can register URL and sitemap knowledge sources, but the worker does not yet have a safe outbound fetch boundary. A normal HTTP client is unsafe here because DNS rebinding, redirects, internal address ranges, response compression, unbounded bodies, or permissive domain matching can turn a public-source fetch into SSRF or resource exhaustion.

The worker is still a minimal durable-execution scaffold and has no HTTP-client dependency. V1.3.05 must therefore establish one reusable internal security primitive without adding a public API, persistence contract, scheduler, crawler, or new service.

## Options considered

### Option A — Use a normal redirect-following HTTP client

Rejected. Automatic DNS resolution and redirect following make it difficult to prove that every destination was validated immediately before connection or that the connected peer matched the validated address.

### Option B — Validate the initial URL once, then use the standard client normally

Rejected. This leaves redirect-to-private and DNS-rebinding gaps.

### Option C — Resolve, validate, pin, and revalidate each hop

Selected. Serviq resolves every hop, rejects the full request when any returned address is non-public, connects directly to one validated address, preserves TLS hostname verification, verifies the connected peer, and handles redirects manually.

## Decision

### URL and domain boundary

- HTTPS only.
- Port 443 only, whether implicit or explicit.
- Reject credentials, fragments, whitespace/control characters, malformed URLs, and relative URLs.
- The caller supplies an explicit exact-host allowlist. Wildcards and suffix matching are not supported.
- Hostnames are normalized through IDNA, lowercase conversion, and removal of one trailing dot.

The helper does not decide whether a source is legally or operationally permitted. A later caller must pass only source-manifest entries already approved for automated access. V1.3.05 never authorizes broad DoorDash or Stripe crawling.

### DNS and network boundary

Before every request, including every redirect target:

1. resolve A/AAAA addresses for TCP/443;
2. fail closed if resolution is empty or fails;
3. fail closed if any answer is not globally routable;
4. explicitly reject private, loopback, link-local, multicast, reserved, unspecified, CGNAT, metadata, documentation/benchmark, and other non-global IPv4/IPv6 space;
5. select one validated address and connect directly to it, avoiding a second hostname lookup;
6. preserve TLS SNI and certificate hostname verification for the original hostname;
7. verify the connected peer address exactly matches the selected validated address and is still public.

The helper does not automatically retry another DNS answer. Retry policy belongs to the owning job layer so retries remain bounded and observable.

### Redirect boundary

Only 301, 302, 303, 307, and 308 are followed. Redirect handling is manual and limited to five hops. Missing `Location` is a terminal failure. Each resolved target must pass the complete URL, allowlist, DNS, IP, TLS, and peer checks again before any request is sent.

### Response boundary

The helper performs GET only and sends `Accept-Encoding: identity`. Non-identity response encoding is rejected.

Allowed MIME types are:

- `text/html`
- `application/xhtml+xml`
- `text/plain`
- `text/markdown`
- `application/xml`
- `text/xml`
- `application/rss+xml`
- `application/atom+xml`

The default response body limit is 5 MiB (5,242,880 bytes). A caller may choose a smaller or larger value only up to the hard V1 ceiling of 50 MiB (52,428,800 bytes). Declared `Content-Length` is checked before body reads and the same limit is enforced while streaming.

The default socket/request timeout is 10 seconds, with a hard V1 ceiling of 30 seconds.

### Error and retry contract

Failures expose only a stable error code and `retryable` boolean. Raw response bodies, DNS details, socket details, credentials, tokens, and remote error messages are not included.

The helper never retries. HTTP 408, 425, 429, and 5xx are classified retryable. Other non-2xx final responses are terminal. DNS, timeout, TLS, and transport failures are classified retryable without exposing their raw details.

## Non-goals

This ticket does not implement crawl scheduling or rate policy, robots/terms evaluation, sitemap traversal, parsing, chunking, embeddings, indexing, persistence, knowledge-source status transitions, a broker consumer, or UI/API changes.

## Security consequences

The design prevents the high-risk SSRF paths in the frozen ticket: direct private targets, cloud metadata, mixed public/private DNS answers, redirect-to-private, and DNS rebinding between validation and connection. It also bounds response memory and rejects compressed payload expansion.

The main availability tradeoff is deliberate fail-closed behavior. A hostname returning any non-public address is rejected even if it also returns a public address. A caller must not weaken this invariant to improve reachability.

## Compatibility and rollback

This is an additive internal worker helper. It changes no public API, database schema, event contract, permission, or existing runtime path. Before a later crawler uses it, the caller must provide an approved exact-host policy.

Rollback is deletion of the helper and its caller integration. V1.3.05 itself has no migration or durable state to reconcile. Once a production caller depends on this helper, rollback must disable that caller rather than substitute an unrestricted HTTP client.

## Verification

Required coverage includes public success, loopback/private/metadata/CGNAT/IPv6 rejection, mixed DNS answers, strict URL/domain checks, public redirect success, redirect-to-private rejection, redirect limits, MIME/encoding checks, declared and streamed body limits, peer mismatch, safe transport errors, retryability classification, and policy-bound validation.
