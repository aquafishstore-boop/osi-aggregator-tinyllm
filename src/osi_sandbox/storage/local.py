"""Local filesystem storage backend (no authentication required)."""

from __future__ import annotations

from pathlib import Path

from osi_sandbox.storage.base import StorageBackend, normalize_key


class LocalStorageBackend(StorageBackend):
    kind = "local"

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        norm = normalize_key(key)
        target = (self.root / norm).resolve()
        # Defense in depth: ensure the resolved path stays under root.
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"Key escapes storage root: {key!r}") from exc
        return target

    def put_bytes(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get_bytes(self, key: str) -> bytes | None:
        path = self._path(key)
        if not path.is_file():
            return None
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def list_children(self, prefix: str) -> list[str]:
        base = self.root if prefix in ("", "/") else self._path(prefix)
        if not base.is_dir():
            return []
        return sorted(p.name for p in base.iterdir())
