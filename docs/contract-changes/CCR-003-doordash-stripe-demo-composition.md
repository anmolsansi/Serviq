# Contract Change Record: CCR-003 — DoorDash + Stripe Demo Composition

**Status:** Applied to OPE-251 decision record  
**Date:** 2026-08-13  
**Linear:** OPE-251  
**GitHub:** #2  
**Supersedes:** CCR-002 for the V1 demo-company/domain decision only  
**Code impact:** No production implementation in this ticket. This record freezes the downstream demo behavior.

## 1. Decision

Serviq Production V1 will use a **combined reference configuration**:

- **DoorDash public customer-support documentation** is the primary customer-operations knowledge domain for delivery, order, missing/incorrect-item, refund/credit, and support-resolution scenarios.
- **Stripe public payment/refund documentation** is the payment-system knowledge domain and the reference payment-provider contract used by the synthetic operational adapter.
- All private customer, order, delivery, payment, refund, and support data remains **synthetic**.
- The V1 mutation path never moves real money and never modifies real DoorDash or Stripe systems.

This combination intentionally demonstrates that Serviq can reason across more than one business system: a customer-facing delivery/support domain and a separate payment provider.

## 2. Why the combined model is stronger

A Stripe-only demo proved payment support well but did not demonstrate the broader customer-operations product Serviq is intended to become. A DoorDash-like delivery workflow is much closer to the full customer journey Serviq should handle: order placed, fulfillment, delivery state, missing/incorrect items, refund eligibility, escalation, and resolution.

Keeping Stripe as the payment-provider layer adds a second operational boundary and proves that Serviq is not hard-coded to a single backend. The resulting reference flow becomes:

```text
Customer question/request
        |
        v
DoorDash public support knowledge
        +
Synthetic customer/order/delivery state
        |
        v
Serviq policy + agent runtime
        |
        +---- read delivery/order state
        +---- evaluate resolution/refund eligibility
        +---- protected refund mutation
                         |
                         v
              synthetic Stripe-shaped
                 payment adapter
```

This is an architectural reference configuration only. It does **not** assert that DoorDash uses Stripe for its production payment processing.

## 3. Public knowledge sources

### DoorDash domain

The source manifest may include an explicit allowlist of customer/merchant help articles required by V1 scenarios, such as:

- missing or incorrect items;
- delivery/order support and order-status concepts;
- refund/credit/redelivery resolution concepts;
- merchant refund/support flows where useful for the human-support console.

The repository stores source URLs/provenance and evaluation fixtures, not a wholesale copy of the DoorDash Help Center.

### Stripe domain

The source manifest may include the Stripe documentation required for:

- payment lifecycle/status concepts;
- refund behavior;
- partial refunds;
- refund state and failure behavior;
- test-mode/reference payment semantics.

The repository stores URLs/provenance and Serviq-authored test fixtures rather than republishing the Stripe documentation corpus.

Every source remains subject to the Serviq ingestion controls: explicit allowlist, access checks, SSRF protection, redirect validation, content-size/type limits, provenance, disable-on-access-change behavior, and no bypassing authentication or anti-bot restrictions.

## 4. Frozen V1 domain constants

```text
demoCompany = "DoorDash reference support domain"
paymentProvider = "Stripe reference payment domain"
publicSourceManifestPolicy = "doordash-stripe-allowlist-v1"
statusToolKey = "demo.get_delivery_order_status"
eligibilityToolKey = "demo.check_order_resolution_eligibility"
mutationToolKey = "demo.create_refund"
```

These are Serviq demo contract identifiers. They are not claims about DoorDash internal system names or integrations.

## 5. Synthetic private-data model

Required synthetic entities are:

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

### `demo_customers`

Tenant-scoped synthetic customer identity and support-facing metadata. No real PII.

### `demo_orders`

Synthetic order header containing order reference, customer reference, merchant reference, subtotal/tax/fees/tip/total in minor units, order status, created time, and current resolution state.

### `demo_order_items`

Synthetic item-level quantities, fulfillment state, substitution/missing/incorrect flags, and refundable amount attribution.

### `demo_deliveries`

Synthetic delivery state such as preparing, awaiting pickup, picked up, in transit, delivered, canceled, or delivery issue. Includes synthetic ETA/status timestamps only.

### `demo_order_events`

Ordered lifecycle events used by Serviq to explain state transitions and provide deterministic support context.

### `demo_payments`

Synthetic Stripe-shaped payment record linked to a synthetic order. It may model payment/refund semantics but does not represent a real Stripe account object or transaction.

### `demo_refund_rules`

Synthetic tenant policy inputs for missing-item, incorrect-item, undelivered-order, partial-refund, full-refund, customer-confirmation, and human-approval decisions.

### `demo_refunds`

Idempotent synthetic refund records with payment/order reference, amount, reason, policy decision, confirmation/approval linkage, status, and timestamps.

### `demo_support_cases`

Synthetic escalations/support-case context for human handoff, resolution, notes, and QA/evaluation scenarios.

## 6. Frozen tool contracts

### 6.1 `demo.get_delivery_order_status`

**Class:** read-only status lookup.

Returns verified synthetic order and delivery state for a customer-scoped order reference.

Minimum input:

```json
{
  "customerId": "uuid",
  "orderId": "string"
}
```

Minimum output:

```json
{
  "orderId": "string",
  "orderStatus": "placed|confirmed|preparing|ready_for_pickup|picked_up|in_transit|delivered|canceled|issue",
  "deliveryStatus": "not_started|awaiting_pickup|in_transit|delivered|failed|canceled",
  "eta": "iso8601|null",
  "lastEventCode": "string",
  "lastEventAt": "iso8601"
}
```

No mutation occurs.

### 6.2 `demo.check_order_resolution_eligibility`

**Class:** read-only eligibility/policy lookup.

Evaluates a synthetic order issue against the order/item/delivery/payment state and Serviq demo resolution rules.

Minimum input:

```json
{
  "customerId": "uuid",
  "orderId": "string",
  "issueType": "missing_item|incorrect_item|order_not_received|late_delivery|duplicate_charge|other",
  "requestedResolution": "refund|partial_refund|credit|redelivery|human_support"
}
```

Minimum output:

```json
{
  "eligible": true,
  "allowedResolutions": ["partial_refund"],
  "maxRefundableAmountMinor": 0,
  "currency": "ISO-4217",
  "reasonCodes": ["string"],
  "requiresCustomerConfirmation": true,
  "requiresHumanApproval": false
}
```

The tool calculates eligibility but does not itself authorize or execute a mutation.

### 6.3 `demo.create_refund`

**Class:** protected mutation.

Creates an idempotent refund in the Serviq synthetic payment adapter after MAS-8 identity, policy, confirmation, and approval requirements have been satisfied.

Minimum input:

```json
{
  "customerId": "uuid",
  "orderId": "string",
  "paymentId": "string",
  "amountMinor": 0,
  "currency": "ISO-4217",
  "reasonCode": "missing_item|incorrect_item|order_not_received|duplicate_charge|service_issue|other",
  "idempotencyKey": "string"
}
```

Minimum output:

```json
{
  "refundId": "string",
  "orderId": "string",
  "paymentId": "string",
  "status": "pending|succeeded|failed|unknown",
  "amountMinor": 0,
  "currency": "ISO-4217",
  "createdAt": "iso8601"
}
```

Rules:

- V1 modifies only synthetic Serviq records.
- The Stripe relationship is a reference adapter contract; no real Stripe key is required for deterministic development or CI.
- A later integration ticket may add an optional Stripe test-mode adapter behind the same Serviq tool contract.
- Unknown mutation outcome goes to reconciliation and is never blindly retried.
- Customer confirmation is required for the reference refund flow.
- Human approval is required when the configured synthetic policy threshold or issue class requires it.

## 7. V1 reference scenarios

The combined configuration must support at least these end-to-end demonstrations:

1. Ask a general delivery/support-policy question and answer from approved public knowledge.
2. Ask "Where is my order?" and resolve it from synthetic order/delivery data without an LLM-dependent business-state guess.
3. Report a missing or incorrect item and retrieve the relevant support guidance.
4. Evaluate resolution/refund eligibility using synthetic order/item/delivery/payment state.
5. Require customer confirmation for a refund.
6. Require human approval for a configured high-value or policy-sensitive refund.
7. Create an idempotent synthetic refund.
8. Simulate a failed/unknown payment-provider outcome and reconcile/escalate safely.
9. Hand the case to a human with order, delivery, payment, evidence, tool history, and policy context already prepared.
10. Trace the entire operation through analytics, audit, and correlation IDs.

## 8. Non-affiliation wording

Use this wording when the reference configuration is shown publicly:

> **Demo disclaimer:** Serviq is an independent portfolio project and is not affiliated with, endorsed by, sponsored by, or connected with DoorDash, Inc. or Stripe, Inc. DoorDash and Stripe names and publicly available documentation are referenced only to demonstrate Serviq customer-support and payment-workflow capabilities. All customers, orders, deliveries, payments, refunds, support cases, and operational records shown by Serviq are synthetic. The reference demo does not access DoorDash private systems and does not execute real DoorDash or Stripe transactions.

## 9. Supersession and downstream impact

CCR-003 supersedes the Stripe-only domain freeze in CCR-002. CCR-002 remains in Git history to document why the decision changed; builders must implement CCR-003.

Downstream impact:

- MAS-3 knowledge fixtures may use `doordash-stripe-allowlist-v1`.
- MAS-4 evaluation scenarios should include both support-policy and payment/refund grounding.
- MAS-7 implements the three tool keys frozen above.
- MAS-8 gets realistic confirmation and approval rules over order/refund state.
- MAS-9 handoff packages include order, delivery, payment, and refund context.
- MAS-11 analytics can separate support-domain retrieval, deterministic order lookups, payment-provider calls, refund attempts, and escalations.

## 10. Remaining product decision

The end-customer file/image attachment decision is still unresolved and is not changed by this CCR.
