# @serviq/config

`@serviq/config` owns shared TypeScript configuration helpers only after their contracts are explicitly defined.

It may eventually contain reusable configuration schemas, normalized configuration types, and safe shared parsing helpers. It must not own product feature logic, secrets, runtime environment values, provider credentials, or application-specific configuration. It must never import from `apps/`.

The package intentionally exports no behavior in this scaffold.
