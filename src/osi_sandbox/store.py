"""Snapshot and report persistence under DATA_DIR."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from osi_sandbox.config import Settings, get_settings


def utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class Store:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = Path(self.settings.data_dir)
        self.snapshots = self.root / "snapshots"
        self.reports = self.root / "reports"
        self.status_path = self.root / "status.json"
        self.snapshots.mkdir(parents=True, exist_ok=True)
        self.reports.mkdir(parents=True, exist_ok=True)

    def write_status(self, payload: dict[str, Any]) -> None:
        self.status_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    def read_status(self) -> dict[str, Any] | None:
        if not self.status_path.exists():
            return None
        try:
            return json.loads(self.status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def create_run(self, run_id: str | None = None) -> str:
        rid = self._safe_segment(run_id or utc_run_id(), kind="run_id")
        (self.snapshots / rid).mkdir(parents=True, exist_ok=True)
        (self.reports / rid).mkdir(parents=True, exist_ok=True)
        return rid

    @staticmethod
    def _safe_segment(name: str, *, kind: str = "id") -> str:
        if not name or name in (".", "..") or "/" in name or "\\" in name or ".." in name:
            raise ValueError(f"Invalid {kind}: {name!r}")
        return name

    def _resolve_under(self, base: Path, *parts: str) -> Path:
        """Resolve a path and ensure it stays under ``base`` (no traversal)."""
        target = (base.joinpath(*parts)).resolve()
        base_resolved = base.resolve()
        try:
            target.relative_to(base_resolved)
        except ValueError as exc:
            raise ValueError(f"Path escapes data directory: {target}") from exc
        return target

    def write_raw(self, run_id: str, feed_id: str, data: Any) -> Path:
        run_id = self._safe_segment(run_id, kind="run_id")
        feed_id = self._safe_segment(feed_id, kind="feed_id")
        path = self._resolve_under(self.snapshots, run_id, f"{feed_id}.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return path

    def write_consolidated(self, run_id: str, data: dict[str, Any]) -> Path:
        run_id = self._safe_segment(run_id, kind="run_id")
        path = self._resolve_under(self.snapshots, run_id, "consolidated.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return path

    def write_report_text(self, run_id: str, name: str, text: str) -> Path:
        run_id = self._safe_segment(run_id, kind="run_id")
        name = self._safe_segment(name, kind="report_name")
        path = self._resolve_under(self.reports, run_id, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def write_meta(self, run_id: str, meta: dict[str, Any]) -> Path:
        run_id = self._safe_segment(run_id, kind="run_id")
        path = self._resolve_under(self.reports, run_id, "meta.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
        return path

    def latest_run_id(self) -> str | None:
        runs = sorted(
            [p.name for p in self.reports.iterdir() if p.is_dir()],
            reverse=True,
        )
        return runs[0] if runs else None

    def list_runs(self, limit: int = 20) -> list[str]:
        runs = sorted(
            [p.name for p in self.reports.iterdir() if p.is_dir()],
            reverse=True,
        )
        return runs[:limit]

    def read_report(self, run_id: str, name: str) -> str | None:
        run_id = self._safe_segment(run_id, kind="run_id")
        name = self._safe_segment(name, kind="report_name")
        path = self._resolve_under(self.reports, run_id, name)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def read_meta(self, run_id: str) -> dict[str, Any] | None:
        run_id = self._safe_segment(run_id, kind="run_id")
        path = self._resolve_under(self.reports, run_id, "meta.json")
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def read_consolidated(self, run_id: str) -> dict[str, Any] | None:
        run_id = self._safe_segment(run_id, kind="run_id")
        path = self._resolve_under(self.snapshots, run_id, "consolidated.json")
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def prior_stats(self, before_run_id: str | None = None) -> dict[str, Any] | None:
        runs = self.list_runs(limit=50)
        for rid in runs:
            if before_run_id and rid >= before_run_id:
                continue
            consolidated = self.read_consolidated(rid)
            if consolidated and isinstance(consolidated.get("stats"), dict):
                return consolidated["stats"]
        return None