# @serviq/ui

`@serviq/ui` is the single shared visual-primitives and design-token package for Serviq web applications.

## What belongs here

- Serviq-owned reusable visual primitives after their contracts are explicitly defined.
- Shared design tokens and accessibility-oriented visual foundations.
- Presentation-only helpers that are genuinely reusable across more than one Serviq web surface.

## What does not belong here

- Product or feature business logic.
- API calls, authentication, tenant logic, or server-state ownership.
- Imports from `apps/client-console`, `apps/customer-web`, or `apps/platform-console`.
- Components copied from one app before a shared contract is deliberately designed.

The package currently exports no components. `./tokens.css` is exposed as the only shared styling asset while the final Serviq design system remains a later ticket.
