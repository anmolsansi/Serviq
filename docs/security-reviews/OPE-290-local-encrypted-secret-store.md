# OPE-290 — Local encrypted tenant-secret store security review

## Scope

This review covers the local V1 `TenantSecretStore` contract and `LocalEncryptedSecretStore`. It does not approve an AWS production secret-store implementation or provider CRUD behavior.

## Key material

The repository already freezes `SESSION_SECRET` as an architecture-owned platform bootstrap secret and prohibits adding environment names in OPE-290. ADR-008 therefore derives a separate 32-byte key with `cryptography` HKDF-SHA256 and a fixed purpose-specific info string. The raw session secret is never used directly by Fernet.

A different bootstrap secret cannot decrypt an existing file and returns the same generic unavailable-secret failure used for corrupt ciphertext.

## Encryption

The implementation uses `cryptography.fernet.Fernet`, not custom encryption. Fernet provides authenticated encryption; modified ciphertext fails authentication before plaintext is returned.

Plaintext is obtained from `SecretStr` only immediately before encryption or immediately after successful decryption. Python cannot guarantee memory zeroization, so the implementation makes no such claim.

## Opaque references and tenant ownership

References are generated from `secrets.token_urlsafe(24)` and prefixed only with `sr_`. They contain neither tenant identifiers nor secret material.

Each encrypted record includes the owning tenant UUID. `get_secret` and `delete_secret` require both tenant ID and ref. A correct ref presented under another tenant produces `SECRET_NOT_FOUND` without attempting to return plaintext.

## Persistence and filesystem safety

The default path is `.local/tenant-secrets.json`, already ignored by repository policy. Writes are serialized inside the process, written to a temporary file, flushed/fsynced, then atomically replaced. POSIX directory/file modes are forced to `0700` and `0600` respectively.

The encrypted file contains tenant UUIDs, opaque refs, and authenticated ciphertext. It does not contain plaintext provider keys.

## Error and logging safety

Public adapter errors are intentionally generic and do not include plaintext, ciphertext, bootstrap keys, or filesystem paths. `repr(LocalEncryptedSecretStore)` is explicitly redacted. Tests verify the fake provider secret is absent from captured logs and persisted content.

## Failure modes reviewed

Automated tests cover:

- put/get roundtrip;
- restart with the same bootstrap key;
- persisted data differing from plaintext;
- opaque refs;
- cross-tenant read rejection;
- delete and unknown-ref behavior;
- corrupt ciphertext;
- wrong bootstrap key;
- redaction-safe representation/log behavior;
- restrictive POSIX modes.

## Residual risks and production boundary

This local file adapter is intentionally a developer/V1 local implementation. It does not provide multi-host synchronization, hardware-backed key management, independent key rotation, or managed audit controls. Production AWS deployment must replace it through the same `TenantSecretStore` protocol with the architecture-approved managed secret store.

## Conclusion

The OPE-290 implementation uses approved cryptography, domain-separated bootstrap key derivation, tenant-bound opaque references, authenticated encryption, restrictive local persistence, and fail-closed errors without introducing a new environment contract or plaintext relational storage.