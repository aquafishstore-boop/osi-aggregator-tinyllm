"""Thin FastAPI surface for triggering runs and reading reports."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from osi_sandbox.config import get_settings
from osi_sandbox.feeds import CORE_FEED_IDS, DENIED_PATHS, FEEDS, SYSTEM_FEED_IDS
from osi_sandbox.pipeline import run_pipeline
from osi_sandbox.storage import describe_storage
from osi_sandbox.store import Store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("osi_sandbox.api")

app = FastAPI(
    title="OSIRIS Sandbox Aggregator",
    version="0.1.0",
    description="Passive feed ingest + local tiny-LLM broad/fine analysis",
)

_run_lock = asyncio.Lock()
_background_task: asyncio.Task[Any] | None = None


class RunRequest(BaseModel):
    mode: Literal["ingest", "broad", "full"] = "full"
    focus: str | None = Field(default=None, description="Fine-pass feed id")
    wait: bool = Field(
        default=False,
        description="If true, await completion; otherwise start in background",
    )


@app.get("/health")
async def health() -> dict[str, Any]:
    settings = get_settings()
    storage = describe_storage(settings)
    return {
        "ok": True,
        "service": "osi-sandbox",
        "osiris_base_url": settings.osiris_base_url,
        "ollama_model": settings.ollama_model,
        "storage": {
            "backend": storage["backend"],
            "encrypted": storage["encrypted"],
            "auth": storage["auth"],
            "ok": storage["ok"],
        },
    }


@app.get("/storage")
async def storage_status() -> dict[str, Any]:
    """Report the configured storage backend + auth posture (no secrets)."""
    return describe_storage(get_settings())


@app.get("/status")
async def status() -> dict[str, Any]:
    store = Store()
    payload = store.read_status() or {"state": "idle", "run_id": None}
    payload["latest_run_id"] = store.latest_run_id()
    payload["running"] = _run_lock.locked()
    return payload


@app.get("/feeds")
async def list_feeds() -> dict[str, Any]:
    return {
        "system": list(SYSTEM_FEED_IDS),
        "core": list(CORE_FEED_IDS),
        "on_demand": [f.id for f in FEEDS.values() if f.group == "on_demand"],
        "denied_paths": sorted(DENIED_PATHS),
        "catalog": {
            fid: {"path": spec.path, "group": spec.group, "description": spec.description}
            for fid, spec in FEEDS.items()
        },
    }


@app.post("/run")
async def trigger_run(body: RunRequest) -> dict[str, Any]:
    global _background_task

    if _run_lock.locked():
        raise HTTPException(status_code=409, detail="A run is already in progress")

    if body.focus and body.focus not in FEEDS:
        raise HTTPException(status_code=400, detail=f"Unknown focus feed: {body.focus}")

    async def _job() -> dict[str, Any]:
        async with _run_lock:
            return await run_pipeline(mode=body.mode, focus=body.focus)

    if body.wait:
        return await _job()

    if _background_task and not _background_task.done():
        raise HTTPException(status_code=409, detail="A run is already in progress")

    _background_task = asyncio.create_task(_job())

    def _done(task: asyncio.Task[Any]) -> None:
        try:
            task.result()
        except Exception:
            logger.exception("Background run failed")

    _background_task.add_done_callback(_done)
    return {"accepted": True, "mode": body.mode, "focus": body.focus}


@app.get("/reports")
async def list_reports(limit: int = 20) -> dict[str, Any]:
    store = Store()
    return {"runs": store.list_runs(limit=limit)}


@app.get("/reports/latest")
async def latest_report() -> dict[str, Any]:
    store = Store()
    run_id = store.latest_run_id()
    if not run_id:
        raise HTTPException(status_code=404, detail="No reports yet")
    return await get_report(run_id)


def _safe_run_id(run_id: str) -> str:
    """Reject path traversal / separator abuse in run ids."""
    if not run_id or run_id in (".", "..") or "/" in run_id or "\\" in run_id or ".." in run_id:
        raise HTTPException(status_code=400, detail="Invalid run_id")
    return run_id


@app.get("/reports/{run_id}")
async def get_report(run_id: str) -> dict[str, Any]:
    run_id = _safe_run_id(run_id)
    store = Store()
    meta = store.read_meta(run_id)
    if meta is None and not store.report_exists(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "run_id": run_id,
        "meta": meta,
        "broad": store.read_report(run_id, "broad.md"),
        "fine": store.read_report(run_id, "fine.md"),
        "consolidated": store.read_consolidated(run_id),
    }


@app.get("/reports/{run_id}/broad.md", response_class=PlainTextResponse)
async def broad_md(run_id: str) -> str:
    run_id = _safe_run_id(run_id)
    text = Store().read_report(run_id, "broad.md")
    if text is None:
        raise HTTPException(status_code=404, detail="broad.md not found")
    return text


@app.get("/reports/{run_id}/fine.md", response_class=PlainTextResponse)
async def fine_md(run_id: str) -> str:
    run_id = _safe_run_id(run_id)
    text = Store().read_report(run_id, "fine.md")
    if text is None:
        raise HTTPException(status_code=404, detail="fine.md not found")
    return text


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "osi_sandbox.api:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()