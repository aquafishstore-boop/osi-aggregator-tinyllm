"""Transparent client-side encryption wrapper around any storage backend.

Uses Fernet (AES-128-CBC + HMAC-SHA256) from ``cryptography``. Payloads are
encrypted before they leave the process, so cloud/remote backends only ever
see ciphertext. The key is required and never persisted by this class.
"""

from __future__ import annotations

from osi_sandbox.storage.base import StorageBackend
from osi_sandbox.storage.errors import StorageConfigError


class EncryptedStorageBackend(StorageBackend):
    def __init__(self, inner: StorageBackend, key: str | bytes) -> None:
        try:
            from cryptography.fernet import Fernet
        except ImportError as exc:  # pragma: no cover - dependency guaranteed in reqs
            raise StorageConfigError(
                "encryption requires the 'cryptography' package"
            ) from exc

        if not key:
            raise StorageConfigError(
                "encrypted storage requires STORAGE_ENCRYPTION_KEY (a Fernet key)"
            )
        key_bytes = key.encode("utf-8") if isinstance(key, str) else key
        try:
            self._fernet = Fernet(key_bytes)
        except (ValueError, TypeError) as exc:
            raise StorageConfigError(
                "STORAGE_ENCRYPTION_KEY is not a valid Fernet key "
                "(generate with Fernet.generate_key())"
            ) from exc

        self._inner = inner
        self.kind = f"{inner.kind}+encrypted"
        self.encrypted = True

    def put_bytes(self, key: str, data: bytes) -> None:
        self._inner.put_bytes(key, self._fernet.encrypt(data))

    def get_bytes(self, key: str) -> bytes | None:
        raw = self._inner.get_bytes(key)
        if raw is None:
            return None
        from cryptography.fernet import InvalidToken

        try:
            return self._fernet.decrypt(raw)
        except InvalidToken as exc:
            raise StorageConfigError(
                f"failed to decrypt {key!r}: wrong key or corrupted ciphertext"
            ) from exc

    def exists(self, key: str) -> bool:
        return self._inner.exists(key)

    def list_children(self, prefix: str) -> list[str]:
        return self._inner.list_children(prefix)
