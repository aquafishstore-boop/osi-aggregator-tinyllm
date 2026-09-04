"""Snapshot / report / agentic-output persistence via a pluggable backend.

The physical destination (local filesystem, S3-compatible object storage, or a
token-authenticated HTTP object store, optionally encrypted) is chosen by
settings and constructed in :func:`osi_sandbox.storage.build_storage`. This
class only deals in logical keys, so the pipeline and API are storage-agnostic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from osi_sandbox.config import Settings, get_settings
from osi_sandbox.storage import StorageBackend, build_storage, describe_storage


def utc_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


class Store:
    def __init__(
        self, settings: Settings | None = None, backend: StorageBackend | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self.backend: StorageBackend = backend or build_storage(self.settings)
        self.status_key = "status.json"

    # -- key helpers ------------------------------------------------------------

    @staticmethod
    def _safe_segment(name: str, *, kind: str = "id") -> str:
        if not name or name in (".", "..") or "/" in name or "\\" in name or ".." in name:
            raise ValueError(f"Invalid {kind}: {name!r}")
        return name

    def _snapshot_key(self, run_id: str, name: str) -> str:
        run_id = self._safe_segment(run_id, kind="run_id")
        name = self._safe_segment(name, kind="name")
        return f"snapshots/{run_id}/{name}"

    def _report_key(self, run_id: str, name: str) -> str:
        run_id = self._safe_segment(run_id, kind="run_id")
        name = self._safe_segment(name, kind="report_name")
        return f"reports/{run_id}/{name}"

    # -- status -----------------------------------------------------------------

    def write_status(self, payload: dict[str, Any]) -> None:
        self.backend.put_json(self.status_key, payload)

    def read_status(self) -> dict[str, Any] | None:
        return self.backend.get_json(self.status_key)

    # -- run lifecycle ----------------------------------------------------------

    def create_run(self, run_id: str | None = None) -> str:
        return self._safe_segment(run_id or utc_run_id(), kind="run_id")

    # -- writes -----------------------------------------------------------------

    def write_raw(self, run_id: str, feed_id: str, data: Any) -> str:
        feed_id = self._safe_segment(feed_id, kind="feed_id")
        key = self._snapshot_key(run_id, f"{feed_id}.json")
        self.backend.put_json(key, data)
        return key

    def write_consolidated(self, run_id: str, data: dict[str, Any]) -> str:
        key = self._snapshot_key(run_id, "consolidated.json")
        self.backend.put_json(key, data)
        return key

    def write_report_text(self, run_id: str, name: str, text: str) -> str:
        key = self._report_key(run_id, name)
        self.backend.put_text(key, text)
        return key

    def write_meta(self, run_id: str, meta: dict[str, Any]) -> str:
        key = self._report_key(run_id, "meta.json")
        self.backend.put_json(key, meta)
        return key

    # -- reads ------------------------------------------------------------------

    def read_report(self, run_id: str, name: str) -> str | None:
        return self.backend.get_text(self._report_key(run_id, name))

    def read_meta(self, run_id: str) -> dict[str, Any] | None:
        return self.backend.get_json(self._report_key(run_id, "meta.json"))

    def read_consolidated(self, run_id: str) -> dict[str, Any] | None:
        return self.backend.get_json(self._snapshot_key(run_id, "consolidated.json"))

    def report_exists(self, run_id: str) -> bool:
        run_id = self._safe_segment(run_id, kind="run_id")
        return bool(self.backend.list_children(f"reports/{run_id}"))

    # -- listing ----------------------------------------------------------------

    def latest_run_id(self) -> str | None:
        runs = self.list_runs(limit=1)
        return runs[0] if runs else None

    def list_runs(self, limit: int = 20) -> list[str]:
        runs = sorted(self.backend.list_children("reports"), reverse=True)
        return runs[:limit]

    def prior_stats(self, before_run_id: str | None = None) -> dict[str, Any] | None:
        for rid in self.list_runs(limit=50):
            if before_run_id and rid >= before_run_id:
                continue
            consolidated = self.read_consolidated(rid)
            if consolidated and isinstance(consolidated.get("stats"), dict):
                return consolidated["stats"]
        return None

    # -- introspection ----------------------------------------------------------

    def describe(self) -> dict[str, Any]:
        return describe_storage(self.settings)
