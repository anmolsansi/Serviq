# Serviq Design Mockups

This directory contains the approved high-resolution visual direction for Serviq's primary product surfaces.

| Design | Resolution | Product surface |
| --- | ---: | --- |
| `serviq-client-portal-4k.png` | 3840 × 2160 | Client Operations Console, including the Human Support Workspace |
| `serviq-customer-experience-4k.png` | 3840 × 2160 | End-customer support experience |
| `serviq-platform-operator-4k.png` | 3840 × 2160 | Serviq Platform Operator Console |

## Product Surface Mapping

### Client Operations Console

Used by tenant owners, administrators, support managers and agents, knowledge managers, AI configuration managers, and authorized analysts/auditors. The production information architecture is defined by `../PRD.md` and `../ARCHITECTURE.md`.

The Human Support Workspace is a first-class workflow inside the client application. It is not a separate authorization domain or a fourth standalone frontend application.

### Customer Experience

Used by a Serviq client's end customers for support conversations, grounded answers, protected action confirmations, escalation, human takeover, and feedback.

### Platform Operator Console

Used only by Serviq platform operators. Platform-operator permissions are separate from tenant roles and must not be inferred from the visual mockup.

## Implementation Authority

These images define visual direction, not implementation contracts. When a mockup conflicts with the written product or architecture contracts, the implementation follows this order:

1. `../PRD.md` for Production V1 product scope and Product Decisions.
2. `../ARCHITECTURE.md` for routes, schemas, permissions, states, and system contracts.
3. `../TECH_STACK.md` for approved technologies and dependencies.
4. `../PRODUCT_SPECIFICATION.md` for the long-term product charter.

Builders must not invent missing behavior from a screenshot. Unresolved scope or contract questions are returned as `Needs Product Decision` or `Needs Architect Decision`.

## Frontend Quality Requirements

The final implementation must support the states and behaviors required by the written contracts even when a static mockup does not depict them, including:

- loading states;
- empty states;
- recoverable and terminal error states;
- permission-denied states where applicable;
- mutation-pending and success/failure feedback;
- responsive layouts;
- keyboard accessibility and accessible labels;
- customer-safe streaming states without exposing internal reasoning;
- sensitive-action confirmation and approval states;
- escalation and human-takeover states.

The 4K assets replace earlier compressed WebP previews and remain the visual reference for frontend implementation.