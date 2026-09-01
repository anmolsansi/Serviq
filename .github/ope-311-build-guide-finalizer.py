from __future__ import annotations

from pathlib import Path

GUIDE_MARKER = "# V1.3.05 — SSRF-safe public knowledge fetch boundary"

SECTION = r'''

---

# V1.3.05 — SSRF-safe public knowledge fetch boundary

**GitHub issue:** #191  
**Linear ticket:** OPE-311  
**Architecture decision:** `docs/architecture-decisions/ADR-020-public-knowledge-fetch-safety.md`

## Why this ticket exists

Serviq can register public URL and sitemap knowledge sources, but registration alone is not safe fetching. A worker that follows an arbitrary URL with a normal HTTP client could be redirected toward localhost, a private service, a cloud metadata endpoint, or another non-public address. DNS can also change between validation and connection. An unexpectedly large or compressed response can create a separate resource-exhaustion problem.

V1.3.05 creates the reusable worker security boundary that later crawler and ingestion jobs must use before they download approved public knowledge. It intentionally does not build the crawler, sitemap traversal, parser, embedding pipeline, persistence flow, or source-status workflow.

## Where the implementation lives

The runtime helper is:

```text
services/worker/app/core/public_knowledge_fetch.py
```

The focused regression suite is:

```text
services/worker/tests/test_public_knowledge_fetch.py
```

The detailed decision and tradeoffs are recorded in ADR-020.

## How a caller uses it

A later worker job constructs a `PublicKnowledgeFetchPolicy` with an explicit set of approved exact hostnames, then calls `fetch_public_knowledge(url, policy)`.

The caller does not get wildcard domains, arbitrary ports, HTTP fallback, provider-controlled endpoints, or automatic retries. Source-manifest approval remains a separate product/policy decision. This helper does not turn the DoorDash or Stripe reference domains into broad crawl permission.

## URL and destination rules

Every request must use HTTPS on port 443. Credentials, URL fragments, malformed URLs, and whitespace/control characters are rejected. Host allowlisting is exact after IDNA/lowercase normalization. Wildcard and suffix matching are not supported.

Before the initial request and before every redirect request, the helper resolves DNS for TCP/443. The entire destination fails closed if any returned address is non-public. Private, loopback, link-local, CGNAT, cloud-metadata-style, multicast, reserved, unspecified, documentation/benchmark, and other non-global IPv4 or IPv6 addresses are rejected.

The helper then connects directly to one validated IP instead of resolving the hostname a second time. TLS still verifies the original hostname through SNI and certificate hostname validation. Before any GET is transmitted, Serviq verifies that the connected peer is exactly the selected validated public address. This closes the DNS-rebinding gap between destination validation and the outbound request.

## Redirect behavior

Redirects are manual. Only 301, 302, 303, 307, and 308 are followed, with a maximum of five hops. A missing `Location` fails safely.

Every redirect target repeats the complete URL, exact-host allowlist, DNS, IP classification, TLS, and peer verification sequence. A public page therefore cannot redirect Serviq into localhost or another internal target.

## Response limits

The helper sends `Accept-Encoding: identity` and rejects non-identity response encoding so compressed payload expansion does not bypass the body limit.

Allowed response types are HTML/XHTML, plain text/Markdown, and the approved XML/RSS/Atom types. Other MIME types are rejected.

The default body limit is 5 MiB. Callers may configure a different value only up to the hard V1 ceiling of 50 MiB. `Content-Length` is checked before reading when present, and the same limit is enforced while streaming when length is missing or inaccurate.

The default socket/request timeout is 10 seconds with a hard V1 ceiling of 30 seconds.

## Failure and retry behavior

The helper returns a typed result containing the final URL, status code, normalized MIME type, and raw body bytes on success.

Failures expose only a stable error code plus a `retryable` boolean. Raw response bodies, DNS details, socket details, tokens, credentials, and remote error strings are not copied into the public error text.

The helper never retries by itself. HTTP 408, 425, 429, and 5xx plus DNS/timeout/TLS/transport failures are classified retryable for a later bounded job policy. Other non-2xx responses are terminal.

## Verification

The focused suite covers public success; loopback, RFC1918/private, metadata/link-local, CGNAT, multicast/reserved, and private IPv6 rejection; mixed public/private DNS answers; strict URL and domain validation; allowed public redirects; redirect-to-private and unallowlisted redirects; redirect ceilings; MIME and content-encoding rejection; declared and streamed oversized responses; peer mismatch before request transmission; stable transport failures; retryability classification; and policy bounds.

The implementation adds no database migration, public API, permission, event contract, broker consumer, new service, or third-party runtime dependency. Worker Ruff, strict mypy, pytest, and the repository CI/Security workflows remain the final merge gate.

## Rollback and future use

V1.3.05 is additive and owns no durable state. The helper can be removed before any caller integrates it without a migration. Once a crawler depends on it, rollback must disable that caller rather than substitute an unrestricted HTTP client.

Future crawl scheduling, per-source rate policy, robots/terms evaluation, sitemap traversal, parsing, indexing, persistence, and observability belong to later tickets. Those layers may narrow this security policy but must not bypass or weaken the destination and redirect validation defined here.
'''


guide = Path("docs/SERVIQ_BUILD_GUIDE.md")
text = guide.read_text(encoding="utf-8")
if GUIDE_MARKER not in text:
    guide.write_text(text.rstrip() + SECTION + "\n", encoding="utf-8")
