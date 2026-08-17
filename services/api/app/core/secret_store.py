"""Tenant-scoped secret-store contract and encrypted local V1 implementation."""

from __future__ import annotations

import base64
import json
import os
import secrets
from pathlib import Path
from threading import RLock
from typing import Protocol
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pydantic import SecretStr

from app.core.config import PlatformSettings

_KEY_INFO = b"serviq-local-tenant-secret-store-v1"
_DEFAULT_PATH = Path(".local/tenant-secrets.json")
_FILE_MODE = 0o600
_DIRECTORY_MODE = 0o700


class SecretStoreError(RuntimeError):
    """Base stable tenant-secret adapter error."""


class SecretNotFoundError(SecretStoreError):
    error_code = "SECRET_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Secret is unavailable.")


class SecretDecryptionError(SecretStoreError):
    error_code = "SECRET_DECRYPTION_FAILED"

    def __init__(self) -> None:
        super().__init__("Secret is unavailable.")


class TenantSecretStore(Protocol):
    def put_secret(self, tenant_id: UUID, plaintext: SecretStr) -> str: ...

    def get_secret(self, tenant_id: UUID, secret_ref: str) -> SecretStr: ...

    def delete_secret(self, tenant_id: UUID, secret_ref: str) -> None: ...


class LocalEncryptedSecretStore:
    """File-backed local adapter; plaintext exists only at encrypt/decrypt boundaries."""

    def __init__(self, *, bootstrap_secret: SecretStr, path: Path = _DEFAULT_PATH) -> None:
        self._path = path
        self._fernet = Fernet(_derive_fernet_key(bootstrap_secret))
        self._lock = RLock()

    def __repr__(self) -> str:
        return "<LocalEncryptedSecretStore redacted>"

    def put_secret(self, tenant_id: UUID, plaintext: SecretStr) -> str:
        value = plaintext.get_secret_value()
        if not value:
            raise ValueError("Secret must not be empty.")
        secret_ref = f"sr_{secrets.token_urlsafe(24)}"
        ciphertext = self._fernet.encrypt(value.encode("utf-8")).decode("ascii")
        del value
        with self._lock:
            document = self._read_document()
            records = document.setdefault("records", {})
            assert isinstance(records, dict)
            records[secret_ref] = {
                "tenant_id": str(tenant_id),
                "ciphertext": ciphertext,
            }
            self._write_document(document)
        return secret_ref

    def get_secret(self, tenant_id: UUID, secret_ref: str) -> SecretStr:
        with self._lock:
            record = self._record_for(document=self._read_document(), secret_ref=secret_ref)
        if record.get("tenant_id") != str(tenant_id):
            raise SecretNotFoundError
        ciphertext = record.get("ciphertext")
        if not isinstance(ciphertext, str):
            raise SecretDecryptionError
        try:
            plaintext = self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError, ValueError):
            raise SecretDecryptionError from None
        return SecretStr(plaintext)

    def delete_secret(self, tenant_id: UUID, secret_ref: str) -> None:
        with self._lock:
            document = self._read_document()
            record = self._record_for(document=document, secret_ref=secret_ref)
            if record.get("tenant_id") != str(tenant_id):
                raise SecretNotFoundError
            records = document["records"]
            assert isinstance(records, dict)
            del records[secret_ref]
            self._write_document(document)

    def _record_for(self, *, document: dict[str, object], secret_ref: str) -> dict[str, object]:
        records = document.get("records")
        if not isinstance(records, dict):
            raise SecretNotFoundError
        record = records.get(secret_ref)
        if not isinstance(record, dict):
            raise SecretNotFoundError
        return record

    def _read_document(self) -> dict[str, object]:
        if not self._path.exists():
            return {"version": 1, "records": {}}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise SecretDecryptionError from None
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise SecretDecryptionError
        return payload

    def _write_document(self, document: dict[str, object]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True, mode=_DIRECTORY_MODE)
        if os.name == "posix":
            os.chmod(self._path.parent, _DIRECTORY_MODE)
        temporary = self._path.with_suffix(f"{self._path.suffix}.{secrets.token_hex(8)}.tmp")
        serialized = json.dumps(document, separators=(",", ":"), sort_keys=True)
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                if os.name == "posix":
                    os.chmod(temporary, _FILE_MODE)
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._path)
            if os.name == "posix":
                os.chmod(self._path, _FILE_MODE)
        finally:
            temporary.unlink(missing_ok=True)


def build_local_secret_store(
    settings: PlatformSettings,
    *,
    path: Path = _DEFAULT_PATH,
) -> LocalEncryptedSecretStore:
    """Build the local adapter from the existing architecture-owned bootstrap secret."""

    return LocalEncryptedSecretStore(bootstrap_secret=settings.session_secret, path=path)


def _derive_fernet_key(bootstrap_secret: SecretStr) -> bytes:
    raw = bootstrap_secret.get_secret_value().encode("utf-8")
    if not raw:
        raise ValueError("Bootstrap secret must not be empty.")
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_KEY_INFO,
    ).derive(raw)
    return base64.urlsafe_b64encode(derived)
