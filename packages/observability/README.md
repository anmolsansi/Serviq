# @serviq/observability

`@serviq/observability` is the shared TypeScript boundary for telemetry helpers after their contracts are deliberately defined.

It may eventually own reusable structured-logging adapters, trace/metric helpers, correlation propagation, and browser/server observability utilities. This scaffold does not configure OpenTelemetry, logging backends, metrics, tracing, or external services. The package must not contain feature business logic or import from `apps/`.

The package intentionally exports no behavior in this scaffold.
