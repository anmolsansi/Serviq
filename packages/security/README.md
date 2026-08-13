# @serviq/security

`@serviq/security` is the shared TypeScript boundary for security helpers whose behavior has been explicitly designed and reviewed.

It may eventually contain reusable safe parsing, redaction, request hardening, browser-safe security utilities, or shared permission primitives when a ticket freezes those contracts. This scaffold does not implement authentication, authorization, secret handling, validation, cryptography, or policy logic. It must not import from `apps/`.

The package intentionally exports no behavior in this scaffold.
