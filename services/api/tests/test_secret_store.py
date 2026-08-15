from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.core.secret_store import (
    LocalEncryptedSecretStore,
    SecretDecryptionError,
    SecretNotFoundError,
)

FAKE_SECRET = "sk-fake-serviq-do-not-use-123456"


def _store(path: Path, bootstrap: str = "bootstrap-secret-for-tests-only") -> LocalEncryptedSecretStore:
    return LocalEncryptedSecretStore(
        bootstrap_secret=SecretStr(bootstrap),
        path=path,
    )


def test_put_get_delete_and_tenant_isolation(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "tenant-secrets.json"
    tenant_a = uuid4()
    tenant_b = uuid4()
    store = _store(path)

    secret_ref = store.put_secret(tenant_a, SecretStr(FAKE_SECRET))
    assert store.get_secret(tenant_a, secret_ref).get_secret_value() == FAKE_SECRET

    persisted = path.read_text(encoding="utf-8")
    assert FAKE_SECRET not in persisted
    assert secret_ref in persisted
    assert FAKE_SECRET not in secret_ref
    assert str(tenant_a) not in secret_ref
    assert repr(store) == "<LocalEncryptedSecretStore redacted>"

    with pytest.raises(SecretNotFoundError, match="Secret is unavailable"):
        store.get_secret(tenant_b, secret_ref)
    assert FAKE_SECRET not in caplog.text

    store.delete_secret(tenant_a, secret_ref)
    with pytest.raises(SecretNotFoundError, match="Secret is unavailable"):
        store.get_secret(tenant_a, secret_ref)


def test_unknown_corrupt_and_wrong_key_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "tenant-secrets.json"
    tenant = uuid4()
    store = _store(path)

    with pytest.raises(SecretNotFoundError):
        store.get_secret(tenant, "sr_unknown")

    secret_ref = store.put_secret(tenant, SecretStr(FAKE_SECRET))
    document = json.loads(path.read_text(encoding="utf-8"))
    document["records"][secret_ref]["ciphertext"] = "not-valid-fernet-ciphertext"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(SecretDecryptionError, match="Secret is unavailable"):
        store.get_secret(tenant, secret_ref)

    second_path = tmp_path / "wrong-key.json"
    first = _store(second_path, "bootstrap-key-one")
    second_ref = first.put_secret(tenant, SecretStr(FAKE_SECRET))
    wrong_key_store = _store(second_path, "bootstrap-key-two")
    with pytest.raises(SecretDecryptionError, match="Secret is unavailable"):
        wrong_key_store.get_secret(tenant, second_ref)


def test_store_survives_restart_and_uses_restrictive_permissions(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "tenant-secrets.json"
    tenant = uuid4()
    bootstrap = "stable-bootstrap-key-for-restart-test"
    first = _store(path, bootstrap)
    secret_ref = first.put_secret(tenant, SecretStr(FAKE_SECRET))

    restarted = _store(path, bootstrap)
    assert restarted.get_secret(tenant, secret_ref).get_secret_value() == FAKE_SECRET

    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
