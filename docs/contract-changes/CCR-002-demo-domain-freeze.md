# Contract Change Record: CCR-002 — V1 Public Demo Domain Freeze

**Status:** Decision frozen for OPE-251  
**Date:** 2026-08-13  
**Linear:** OPE-251  
**GitHub:** #2  
**Architect-owned artifacts affected:** PRD demo decision, Product Specification public-demo strategy, Architecture MAS-7/tool contracts  
**Code impact:** No production implementation in this ticket. This record freezes downstream behavior.

## 1. Decision

Serviq Production V1 will use **Stripe public documentation** as the first real-company public knowledge corpus and a **synthetic payment-operations domain** for private operational data.

This is a portfolio/reference configuration only. Serviq is not affiliated with Stripe and does not use Stripe private customer data, private account data, production API credentials, or real payment mutations in the reference demo.

## 2. Candidate comparison

| Candidate | Public documentation coverage | Fit for the three required tool classes | Access / crawl / legal risk for this demo | Portfolio clarity | Decision |
|---|---|---|---|---|---|
| DoorDash | Strong consumer support coverage for delivery issues, missing/incorrect items, credits/refunds, and support resolution. | Strong fit for order status, resolution eligibility, and refund/cancellation-style actions. | **High for automated ingestion.** DoorDash consumer terms surfaced during review prohibit robot/spider/web-crawler/extraction access and systematic retrieval without permission. That conflicts with the ticket requirement to reject a candidate when automated ingestion is unsafe or disallowed. | Very clear consumer-support story. | Rejected for V1 automated knowledge ingestion unless written permission is obtained later. |
| Shopify | Strong merchant documentation for orders, refunds, returns, cancellations, return rules, and APIs. | Strong commerce fit. | **Medium.** Shopify provides formal APIs and developer documentation, but automated access to Shopify services/content is governed by Shopify terms and API licensing. A merchant-specific support demo also introduces ambiguity between Shopify-as-client and a merchant-as-client. | Excellent future integration candidate, especially with development/test stores. | Deferred to a later integration/demo pack. |
| Etsy | Public buyer/seller help content covers returns, exchanges, refunds, purchase protection, and seller policies. | Moderate/strong fit, but eligibility varies substantially by seller policy. | **High for automated site ingestion.** Current Etsy terms/API terms prohibit scraping/crawling and restrict automated collection/AI uses unless expressly authorized. | Recognizable marketplace, but seller-specific policies make one deterministic reference policy less clear. | Rejected for V1 automated knowledge ingestion without authorization. |
| Stripe | Extensive public technical/support documentation covering payment states, declines, refunds, cancellations, disputes, webhooks, and API behavior. Stripe also publishes an LLM-oriented documentation index and Markdown documentation endpoints. | **Strong fit:** payment status lookup, refund eligibility, and protected refund creation can be demonstrated using synthetic records without real money movement. | **Lowest operational ingestion risk of the four for this design** because the docs surface explicitly provides machine-readable/LLM-oriented documentation paths. Serviq still stores only a source manifest/provenance in Git and does not republish the documentation corpus. | Clear AI customer-operations story for payment/support teams and demonstrates RAG + private context + policy + mutation safely. | **Selected.** |

This comparison is an engineering/product suitability assessment, not legal advice. Every manifest entry remains subject to source-access and terms checks at ingestion time.

## 3. Frozen integration constants

```text
demoCompany = "Stripe"
publicSourceManifestPolicy = "stripe-docs-allowlist-v1"
statusToolKey = "demo.get_payment_status"
eligibilityToolKey = "demo.check_refund_eligibility"
mutationToolKey = "demo.create_refund"
```

These values are contract identifiers. Builders must not rename them without a later contract change record.

## 4. Public source-manifest policy

`stripe-docs-allowlist-v1` follows these rules:

1. Git stores **URLs/provenance only**, not a wholesale copy of Stripe documentation.
2. V1 sources are an explicit allowlist. There is no general-purpose recursive crawl or domain discovery.
3. Initial topics are restricted to payment status, declines, refunds/cancellations, disputes, errors, and testing documentation needed by the V1 evaluation scenarios.
4. Prefer Stripe's machine-readable documentation surfaces (including the published LLM documentation index and Markdown page variants) when available.
5. Every source record stores canonical URL, title, topic, access scope, last-verified timestamp, and enabled/disabled state.
6. Redirects, hostnames, content types, size limits, and SSRF protections remain governed by the Architecture ingestion contract.
7. If a source begins requiring authentication, blocks automated access, changes terms in a way incompatible with the use case, or fails the source-access check, Serviq disables that manifest entry rather than bypassing the restriction.
8. Serviq does not present copied Stripe docs as its own documentation and does not imply endorsement or partnership.

## 5. Synthetic operational domain

The private-data side of the V1 demo is **synthetic payment operations**. It represents the kind of account/payment context a payment-support team would need, while ensuring all data is generated by Serviq fixtures.

Required synthetic record types:

```text
demo_customers
demo_payments
demo_payment_events
demo_refund_rules
demo_refunds
```

No real card numbers, bank details, Stripe customer objects, Stripe account data, or real PII are used.

### 5.1 `demo_customers`

Synthetic customer identity and support-facing metadata required to prove tenant/customer scoping. No real PII.

### 5.2 `demo_payments`

Synthetic payment record containing a Serviq-generated payment reference, amount/currency, current status, captured/refundable amounts, created timestamp, synthetic payment-method category, and customer relationship.

### 5.3 `demo_payment_events`

Ordered synthetic lifecycle events used to explain why a payment is `requires_action`, `processing`, `succeeded`, `failed`, `canceled`, partially refunded, or refunded.

### 5.4 `demo_refund_rules`

Synthetic tenant policy inputs used by the eligibility tool. Rules may include allowed payment states, refund window, maximum refundable amount, already-refunded amount, and whether human approval is required above a configured threshold.

### 5.5 `demo_refunds`

Synthetic refund mutation records with idempotency key, payment reference, amount, reason, status, policy decision reference, confirmation/approval reference when applicable, and timestamps.

## 6. Frozen V1 tool contracts

### 6.1 Read-only status tool

**Key:** `demo.get_payment_status`

**Purpose:** Return verified synthetic payment state and a normalized lifecycle summary for a customer-scoped payment reference.

Minimum input contract:

```json
{
  "customerId": "uuid",
  "paymentId": "string"
}
```

Minimum normalized output contract:

```json
{
  "paymentId": "string",
  "status": "requires_action|processing|succeeded|failed|canceled|partially_refunded|refunded",
  "amountMinor": 0,
  "currency": "ISO-4217",
  "refundableAmountMinor": 0,
  "lastEventCode": "string",
  "lastEventAt": "iso8601"
}
```

This tool never mutates state and never calls Stripe in the V1 reference demo.

### 6.2 Eligibility/policy lookup tool

**Key:** `demo.check_refund_eligibility`

**Purpose:** Evaluate a synthetic payment against the frozen demo refund rules and return whether a refund can be requested, the maximum refundable amount, and governance requirements.

Minimum input contract:

```json
{
  "customerId": "uuid",
  "paymentId": "string",
  "requestedAmountMinor": 0,
  "reasonCode": "duplicate|fraudulent|requested_by_customer|service_issue|other"
}
```

Minimum normalized output contract:

```json
{
  "eligible": true,
  "maxRefundableAmountMinor": 0,
  "currency": "ISO-4217",
  "reasonCodes": ["string"],
  "requiresCustomerConfirmation": true,
  "requiresHumanApproval": false
}
```

This is a read-only calculation over synthetic records and Serviq policy. It does not itself authorize or execute the mutation.

### 6.3 Protected mutation tool

**Key:** `demo.create_refund`

**Purpose:** Create an idempotent synthetic refund record after identity, policy, confirmation, and human-approval requirements have been satisfied by Serviq.

Minimum input contract:

```json
{
  "customerId": "uuid",
  "paymentId": "string",
  "amountMinor": 0,
  "currency": "ISO-4217",
  "reasonCode": "duplicate|fraudulent|requested_by_customer|service_issue|other",
  "idempotencyKey": "string"
}
```

Minimum normalized output contract:

```json
{
  "refundId": "string",
  "paymentId": "string",
  "status": "pending|succeeded|failed",
  "amountMinor": 0,
  "currency": "ISO-4217",
  "createdAt": "iso8601"
}
```

Rules:

- V1 reference implementation modifies only Serviq synthetic data; it does not send a refund to Stripe or move money.
- Verified customer context is required.
- A successful `demo.check_refund_eligibility` result does not bypass the MAS-8 policy decision.
- Customer confirmation is required for the reference mutation.
- Human approval is additionally required when the synthetic tenant policy threshold says so.
- The execution is idempotent and an ambiguous outcome enters reconciliation rather than blind retry.

## 7. Required V1 demo scenarios enabled by this decision

The selected domain supports:

1. grounded question about payment/refund behavior from Stripe public documentation;
2. verified synthetic payment-status lookup;
3. refund-eligibility explanation using public knowledge plus synthetic payment state;
4. customer confirmation;
5. human approval above a configured synthetic threshold;
6. successful synthetic refund mutation;
7. deterministic mutation failure/ambiguous outcome simulation;
8. human escalation and support-agent takeover;
9. analytics showing retrieval/model/tool/policy outcomes;
10. audit history linking the policy decision, confirmation/approval, idempotency key, and synthetic mutation.

## 8. Frozen non-affiliation wording

Use the following wording in the public README/demo wherever Stripe is named:

> **Demo disclaimer:** Serviq is an independent portfolio project and is not affiliated with, endorsed by, sponsored by, or connected with Stripe, Inc. Stripe names and public documentation are referenced solely to demonstrate retrieval against publicly available documentation. All customers, payments, events, refunds, support cases, and operational records shown in the Serviq demo are synthetic, and the reference demo does not execute real Stripe transactions.

## 9. Downstream contract impact

- MAS-3 may create the `stripe-docs-allowlist-v1` source-manifest fixture in a later ingestion ticket.
- MAS-4 evaluation fixtures may now name the selected Stripe topics and expected citations.
- MAS-7 tickets must implement only the three frozen demo tool keys above for the first domain pack unless a later ticket explicitly expands scope.
- MAS-8 policy/evaluation tickets can now use refund-specific confirmation and approval scenarios.
- MAS-11 analytics/audit fixtures can use payment/refund event names without inventing an order domain.
- Shopify remains the preferred future commerce integration candidate but is not part of this V1 domain-freeze ticket.

## 10. Superseded Product Decision blocker

This CCR resolves the two open Product Decisions concerning:

- the first real-company public knowledge corpus; and
- the matching synthetic private-data/tool domain.

The separate Product Decision about end-customer file/image attachments is **not** resolved by OPE-251 and remains blocked until its own product decision is made.

## 11. Validation checklist

- [x] One company selected.
- [x] Public source-manifest policy named.
- [x] Three exact tool keys frozen.
- [x] Required synthetic record types named.
- [x] No workflow depends on real PII or private company APIs.
- [x] Protected mutation is synthetic and idempotent.
- [x] Non-affiliation wording frozen.
- [x] Downstream MAS-7 product behavior can now be specified without inventing a domain.
