"""Storage backend + auth-policy tests."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from osi_sandbox.config import Settings
from osi_sandbox.storage import (
    StorageAuthError,
    StorageConfigError,
    build_storage,
    describe_storage,
)
from osi_sandbox.storage.encrypted import EncryptedStorageBackend
from osi_sandbox.storage.http_token import HttpTokenStorageBackend
from osi_sandbox.storage.local import LocalStorageBackend
from tests.http_object_store import running_object_store

TOKEN = "test-pat-123"


# -- local -------------------------------------------------------------------

def test_local_roundtrip_and_listing(tmp_path):
    b = LocalStorageBackend(tmp_path)
    b.put_json("reports/run1/meta.json", {"a": 1})
    b.put_text("reports/run1/broad.md", "# hi")
    assert b.get_json("reports/run1/meta.json") == {"a": 1}
    assert b.get_text("reports/run1/broad.md") == "# hi"
    assert b.exists("reports/run1/meta.json")
    assert not b.exists("reports/missing.json")
    assert b.list_children("reports") == ["run1"]
    assert set(b.list_children("reports/run1")) == {"meta.json", "broad.md"}
    assert b.get_bytes("nope") is None


@pytest.mark.parametrize("bad", ["/abs", "../escape", "a/../../b", ""])
def test_local_rejects_traversal(tmp_path, bad):
    b = LocalStorageBackend(tmp_path)
    with pytest.raises(ValueError):
        b.put_bytes(bad, b"x")


# -- encryption --------------------------------------------------------------

def test_encrypted_hides_plaintext_on_inner(tmp_path):
    inner = LocalStorageBackend(tmp_path)
    enc = EncryptedStorageBackend(inner, Fernet.generate_key())
    enc.put_text("reports/run1/fine.md", "top secret analysis")
    # Round-trips through the wrapper.
    assert enc.get_text("reports/run1/fine.md") == "top secret analysis"
    # Inner bytes are ciphertext, not the plaintext.
    raw = inner.get_bytes("reports/run1/fine.md")
    assert raw is not None
    assert b"top secret analysis" not in raw
    assert enc.encrypted is True
    assert enc.kind == "local+encrypted"


def test_encryption_requires_key(tmp_path):
    with pytest.raises(StorageConfigError):
        EncryptedStorageBackend(LocalStorageBackend(tmp_path), "")


def test_encryption_wrong_key_fails(tmp_path):
    inner = LocalStorageBackend(tmp_path)
    EncryptedStorageBackend(inner, Fernet.generate_key()).put_text("k", "v")
    other = EncryptedStorageBackend(inner, Fernet.generate_key())
    with pytest.raises(StorageConfigError):
        other.get_text("k")


# -- http token backend ------------------------------------------------------

def test_http_backend_roundtrip_with_token():
    with running_object_store(TOKEN) as (base_url, _objects):
        b = HttpTokenStorageBackend(base_url, TOKEN)
        b.put_json("snapshots/run1/health.json", {"ok": True})
        b.put_text("reports/run1/broad.md", "# briefing")
        assert b.get_json("snapshots/run1/health.json") == {"ok": True}
        assert b.exists("reports/run1/broad.md")
        assert not b.exists("reports/run1/missing.md")
        assert b.list_children("reports") == ["run1"]
        assert b.list_children("reports/run1") == ["broad.md"]
        assert b.get_bytes("reports/run1/missing.md") is None


def test_http_backend_requires_token():
    with pytest.raises(StorageAuthError):
        HttpTokenStorageBackend("http://127.0.0.1:1", token=None)
    with pytest.raises(StorageAuthError):
        HttpTokenStorageBackend("http://127.0.0.1:1", token="")


def test_http_backend_rejects_wrong_token():
    with running_object_store(TOKEN) as (base_url, _objects):
        bad = HttpTokenStorageBackend(base_url, "wrong-token")
        with pytest.raises(StorageAuthError):
            bad.put_text("x", "y")


# -- factory / policy enforcement -------------------------------------------

def test_factory_local_needs_no_auth(tmp_path):
    s = Settings(DATA_DIR=str(tmp_path), STORAGE_BACKEND="local")
    backend = build_storage(s)
    assert backend.kind == "local"
    assert describe_storage(s)["auth_required"] is False


def test_factory_http_without_token_fails_closed(tmp_path):
    s = Settings(
        DATA_DIR=str(tmp_path),
        STORAGE_BACKEND="http",
        STORAGE_HTTP_URL="http://example.invalid",
    )
    with pytest.raises(StorageAuthError):
        build_storage(s)
    summary = describe_storage(s)
    assert summary["auth_required"] is True
    assert summary["auth_configured"] is False
    assert summary["ok"] is False


def test_factory_http_with_token_ok(tmp_path):
    s = Settings(
        DATA_DIR=str(tmp_path),
        STORAGE_BACKEND="http",
        STORAGE_HTTP_URL="http://example.invalid",
        STORAGE_HTTP_TOKEN="pat-abc",
    )
    backend = build_storage(s)
    assert backend.kind == "http"
    assert describe_storage(s)["auth_configured"] is True


def test_factory_s3_without_credentials_fails_closed(tmp_path):
    s = Settings(
        DATA_DIR=str(tmp_path),
        STORAGE_BACKEND="s3",
        STORAGE_S3_BUCKET="bucket",
    )
    with pytest.raises((StorageAuthError, StorageConfigError)):
        build_storage(s)
    assert describe_storage(s)["auth_required"] is True


def test_factory_encryption_requires_key(tmp_path):
    s = Settings(
        DATA_DIR=str(tmp_path),
        STORAGE_BACKEND="local",
        STORAGE_ENCRYPTION=True,
    )
    with pytest.raises(StorageConfigError):
        build_storage(s)


def test_factory_unknown_backend(tmp_path):
    s = Settings(DATA_DIR=str(tmp_path), STORAGE_BACKEND="ftp")
    with pytest.raises(StorageConfigError):
        build_storage(s)


def test_encrypted_over_http(tmp_path):
    with running_object_store(TOKEN) as (base_url, objects):
        s = Settings(
            DATA_DIR=str(tmp_path),
            STORAGE_BACKEND="http",
            STORAGE_HTTP_URL=base_url,
            STORAGE_HTTP_TOKEN=TOKEN,
            STORAGE_ENCRYPTION=True,
            STORAGE_ENCRYPTION_KEY=Fernet.generate_key().decode(),
        )
        backend = build_storage(s)
        assert backend.encrypted is True
        backend.put_text("reports/run1/fine.md", "classified")
        assert backend.get_text("reports/run1/fine.md") == "classified"
        # Server stored ciphertext only.
        stored = next(v for k, v in objects.items() if k.endswith("fine.md"))
        assert b"classified" not in stored
