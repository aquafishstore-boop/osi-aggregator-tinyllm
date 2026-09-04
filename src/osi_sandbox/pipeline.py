"""End-to-end ingest → consolidate → broad/fine analysis run."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from osi_sandbox.analyze import OllamaAnalyzer
from osi_sandbox.client import OsirisClient
from osi_sandbox.config import Settings, get_settings
from osi_sandbox.consolidate import consolidate_results, pick_fine_focus
from osi_sandbox.feeds import SYSTEM_FEED_IDS, resolve_core_ids
from osi_sandbox.store import Store, utc_run_id

logger = logging.getLogger(__name__)

Mode = Literal["broad", "full", "ingest"]


async def run_pipeline(
    *,
    mode: Mode = "full",
    focus: str | None = None,
    feed_ids: list[str] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    store = Store(settings)
    run_id = utc_run_id()
    store.create_run(run_id)

    store.write_status(
        {
            "state": "running",
            "run_id": run_id,
            "mode": mode,
            "started_at": datetime.now(UTC).isoformat(),
            "error": None,
        }
    )

    core = feed_ids or resolve_core_ids(settings.core_feed_id_list())
    ids = list(dict.fromkeys([*SYSTEM_FEED_IDS, *core]))

    try:
        async with OsirisClient(settings) as client:
            results = await client.fetch_many(ids)

        for feed_id, result in results.items():
            if result.ok:
                store.write_raw(run_id, feed_id, result.data)
            else:
                store.write_raw(
                    run_id,
                    feed_id,
                    {"error": result.error, "status_code": result.status_code},
                )

        prior = store.prior_stats(before_run_id=run_id)
        consolidated = consolidate_results(results, top_n=settings.top_n, prior_stats=prior)
        consolidated["run_id"] = run_id
        consolidated["source"] = settings.osiris_base_url
        consolidated["fetched_feed_ids"] = ids
        store.write_consolidated(run_id, consolidated)

        meta: dict[str, Any] = {
            "run_id": run_id,
            "mode": mode,
            "focus": focus,
            "osiris_base_url": settings.osiris_base_url,
            "ollama_model": settings.ollama_model,
            "feeds": ids,
            "feed_ok_count": consolidated["feed_ok_count"],
            "feed_error_count": consolidated["feed_error_count"],
            "completed_at": None,
        }

        broad_md = None
        fine_md = None

        if mode in ("broad", "full"):
            analyzer = OllamaAnalyzer(settings)
            logger.info("Running broad analysis for %s", run_id)
            broad_md = await analyzer.broad(consolidated)
            store.write_report_text(run_id, "broad.md", broad_md)

            if mode == "full":
                fine_pack = pick_fine_focus(consolidated, focus=focus)
                meta["fine_focus"] = fine_pack.get("focus")
                logger.info("Running fine analysis focus=%s", fine_pack.get("focus"))
                fine_md = await analyzer.fine(fine_pack, focus=str(fine_pack.get("focus")))
                store.write_report_text(run_id, "fine.md", fine_md)

        meta["completed_at"] = datetime.now(UTC).isoformat()
        store.write_meta(run_id, meta)

        status = {
            "state": "idle",
            "run_id": run_id,
            "mode": mode,
            "finished_at": meta["completed_at"],
            "error": None,
            "latest_report": run_id,
        }
        store.write_status(status)

        return {
            "run_id": run_id,
            "mode": mode,
            "meta": meta,
            "consolidated": consolidated,
            "broad": broad_md,
            "fine": fine_md,
        }
    except Exception as exc:
        logger.exception("pipeline failed")
        store.write_status(
            {
                "state": "error",
                "run_id": run_id,
                "mode": mode,
                "error": str(exc),
                "finished_at": datetime.now(UTC).isoformat(),
            }
        )
        raise