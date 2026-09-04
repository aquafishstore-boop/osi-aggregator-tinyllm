"""Storage backend interface + JSON/text helpers.

Keys are POSIX-style relative paths using ``/`` separators, without a leading
slash, e.g. ``reports/20260904T120000Z/broad.md``. Implementations must reject
absolute keys and ``..`` traversal.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any


def normalize_key(key: str) -> str:
    """Validate and normalize a storage key.

    Rejects empty keys, absolute keys, and any ``.``/``..`` traversal segments.
    """
    if not key or key.startswith("/") or key.startswith("\\"):
        raise ValueError(f"Invalid storage key: {key!r}")
    parts = [p for p in key.replace("\\", "/").split("/") if p != ""]
    if not parts:
        raise ValueError(f"Invalid storage key: {key!r}")
    for part in parts:
        if part in (".", ".."):
            raise ValueError(f"Path traversal in storage key: {key!r}")
    return "/".join(parts)


class StorageBackend(ABC):
    """Content-addressed-ish object store over string keys."""

    #: Human-readable backend kind (e.g. ``local``, ``s3``, ``http``).
    kind: str = "abstract"
    #: Whether payloads are encrypted at rest by this backend (or a wrapper).
    encrypted: bool = False

    @abstractmethod
    def put_bytes(self, key: str, data: bytes) -> None:
        """Write raw bytes at ``key`` (overwrites)."""

    @abstractmethod
    def get_bytes(self, key: str) -> bytes | None:
        """Read raw bytes at ``key`` or ``None`` if absent."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return whether ``key`` exists."""

    @abstractmethod
    def list_children(self, prefix: str) -> list[str]:
        """List immediate child segment names under ``prefix`` (like ``ls``).

        ``prefix`` is a key prefix without a trailing slash (``""`` for root).
        Returns unique next-path-segment names, not full keys.
        """

    # -- text / json convenience -------------------------------------------------

    def put_text(self, key: str, text: str) -> None:
        self.put_bytes(key, text.encode("utf-8"))

    def get_text(self, key: str) -> str | None:
        raw = self.get_bytes(key)
        return None if raw is None else raw.decode("utf-8")

    def put_json(self, key: str, data: Any) -> None:
        self.put_text(key, json.dumps(data, indent=2, default=str))

    def get_json(self, key: str) -> Any | None:
        text = self.get_text(key)
        if text is None:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def health(self) -> dict[str, Any]:
        """Lightweight backend descriptor (no secrets)."""
        return {"kind": self.kind, "encrypted": self.encrypted}
