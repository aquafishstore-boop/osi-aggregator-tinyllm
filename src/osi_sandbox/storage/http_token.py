"""Token-authenticated HTTP object store backend.

A small, provider-agnostic REST contract that works with any object store
fronted by bearer-token auth (an internal artifact store, a signed gateway,
etc.). Every request carries ``Authorization: Bearer <PAT/API token>``.

Contract (relative to ``base_url``):
- ``PUT    /<key>``            body = object bytes            -> 200/201/204
- ``GET    /<key>``            -> 200 + bytes | 404
- ``HEAD   /<key>``            -> 200 | 404
- ``GET    /?prefix=<prefix>`` -> 200 JSON ``{"keys": ["a/b", ...]}``

The token is required; constructing this backend without one raises
:class:`StorageAuthError`.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from osi_sandbox.storage.base import StorageBackend, normalize_key
from osi_sandbox.storage.errors import StorageAuthError, StorageError


class HttpTokenStorageBackend(StorageBackend):
    kind = "http"

    def __init__(
        self,
        base_url: str,
        token: str | None,
        *,
        timeout: float = 30.0,
        verify: bool = True,
    ) -> None:
        if not token:
            raise StorageAuthError(
                "http storage backend requires a PAT / API token "
                "(set STORAGE_HTTP_TOKEN)"
            )
        if not base_url:
            raise StorageError("http storage backend requires STORAGE_HTTP_URL")
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._client = httpx.Client(
            timeout=timeout,
            verify=verify,
            headers={"Authorization": f"Bearer {token}"},
        )

    def _url(self, key: str) -> str:
        norm = normalize_key(key)
        return f"{self.base_url}/{quote(norm)}"

    def put_bytes(self, key: str, data: bytes) -> None:
        resp = self._client.put(
            self._url(key),
            content=data,
            headers={"Content-Type": "application/octet-stream"},
        )
        if resp.status_code == 401 or resp.status_code == 403:
            raise StorageAuthError(f"storage rejected token (HTTP {resp.status_code})")
        if resp.status_code not in (200, 201, 204):
            raise StorageError(f"put {key} failed: HTTP {resp.status_code}")

    def get_bytes(self, key: str) -> bytes | None:
        resp = self._client.get(self._url(key))
        if resp.status_code == 404:
            return None
        if resp.status_code in (401, 403):
            raise StorageAuthError(f"storage rejected token (HTTP {resp.status_code})")
        if resp.status_code != 200:
            raise StorageError(f"get {key} failed: HTTP {resp.status_code}")
        return resp.content

    def exists(self, key: str) -> bool:
        resp = self._client.head(self._url(key))
        if resp.status_code in (401, 403):
            raise StorageAuthError(f"storage rejected token (HTTP {resp.status_code})")
        return resp.status_code == 200

    def list_children(self, prefix: str) -> list[str]:
        norm_prefix = "" if prefix in ("", "/") else normalize_key(prefix)
        resp = self._client.get(self.base_url + "/", params={"prefix": norm_prefix})
        if resp.status_code in (401, 403):
            raise StorageAuthError(f"storage rejected token (HTTP {resp.status_code})")
        if resp.status_code != 200:
            raise StorageError(f"list {prefix!r} failed: HTTP {resp.status_code}")
        payload: Any = resp.json()
        keys: list[str] = payload.get("keys", []) if isinstance(payload, dict) else []
        base = f"{norm_prefix}/" if norm_prefix else ""
        children: set[str] = set()
        for full in keys:
            if base and not full.startswith(base):
                continue
            remainder = full[len(base):]
            if not remainder:
                continue
            children.add(remainder.split("/", 1)[0])
        return sorted(children)
