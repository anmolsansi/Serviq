# ADR-008 — Local tenant-secret store bootstrap key

## Status

Accepted for OPE-290.

## Context

Serviq's frozen environment contract already contains `SESSION_SECRET` as a required platform bootstrap secret. The architecture says local tenant BYOK credentials must use ignored local encrypted storage and must not introduce tenant provider keys into process configuration. OPE-290 explicitly prohibits inventing new environment variable names.

The repository has the approved `cryptography` dependency but no separate frozen `SECRET_STORE_KEY` environment variable.

## Decision

The local V1 secret-store adapter derives a dedicated encryption key from the existing `SESSION_SECRET` with `cryptography` HKDF-SHA256 using the fixed domain-separation info string `serviq-local-tenant-secret-store-v1`.

The raw session secret is **not** used directly as a Fernet key. HKDF produces independent key material for this local secret-store purpose.

The default encrypted file is `.local/tenant-secrets.json`, which is already covered by the repository's `.local/` ignore rule. The adapter constructor accepts an explicit path for tests and future local tooling without adding an environment variable.

## Security consequences

- no new environment/config contract is invented;
- no tenant provider key is placed in environment configuration;
- the secret-store encryption key is cryptographically separated from session-cookie usage;
- changing `SESSION_SECRET` makes existing local ciphertext unreadable, which fails closed and is acceptable for the local V1 adapter;
- production AWS secret storage remains a separate future adapter and is not changed by this decision.

## Scope

This ADR applies only to the local encrypted tenant-secret adapter. It does not define AWS Secrets Manager/Parameter Store selection, production key rotation, provider CRUD, or provider SDK behavior.