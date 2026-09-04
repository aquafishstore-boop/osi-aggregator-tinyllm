"""Reduce raw feed payloads to LLM-sized consolidated packs."""

from __future__ import annotations

from typing import Any

from osi_sandbox.client import FetchResult
from osi_sandbox.feeds import FEEDS


def consolidate_results(
    results: dict[str, FetchResult],
    *,
    top_n: int = 12,
    prior_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    feeds_out: dict[str, Any] = {}
    errors: dict[str, str] = {}

    for feed_id, result in results.items():
        if not result.ok:
            errors[feed_id] = result.error or "fetch failed"
            feeds_out[feed_id] = {
                "ok": False,
                "error": result.error,
                "status_code": result.status_code,
                "elapsed_ms": round(result.elapsed_ms, 1),
            }
            continue
        spec = FEEDS.get(feed_id)
        truncate = spec.truncate if spec else None
        if truncate is None:
            from osi_sandbox.feeds import truncate_generic

            truncate = truncate_generic
        summary = truncate(result.data, top_n)
        feeds_out[feed_id] = {
            "ok": True,
            "path": result.path,
            "status_code": result.status_code,
            "elapsed_ms": round(result.elapsed_ms, 1),
            "cache_ttl_hint": result.cache_ttl_hint,
            "summary": summary,
        }

    stats_block = None
    stats_result = results.get("stats")
    if stats_result and stats_result.ok and isinstance(stats_result.data, dict):
        stats_block = stats_result.data.get("stats", stats_result.data)

    deltas: dict[str, Any] = {}
    if prior_stats and isinstance(stats_block, dict):
        for key, value in stats_block.items():
            if key in prior_stats and isinstance(value, (int, float)) and isinstance(
                prior_stats[key], (int, float)
            ):
                deltas[key] = value - prior_stats[key]

    return {
        "stats": stats_block,
        "stats_delta_vs_prior": deltas or None,
        "feeds": feeds_out,
        "errors": errors,
        "feed_ok_count": sum(1 for r in results.values() if r.ok),
        "feed_error_count": sum(1 for r in results.values() if not r.ok),
    }


def pick_fine_focus(consolidated: dict[str, Any], focus: str | None = None) -> dict[str, Any]:
    """Select one or two feed slices for the fine analysis pass."""
    feeds = consolidated.get("feeds") or {}
    if focus and focus in feeds:
        return {"focus": focus, "slices": {focus: feeds[focus]}}

    candidates = ["earthquakes", "conflicts", "cyber-threats", "fires", "news", "maritime"]
    chosen: list[str] = []
    for cid in candidates:
        if cid in feeds and feeds[cid].get("ok"):
            chosen.append(cid)
        if len(chosen) >= 2:
            break
    if not chosen:
        for fid, body in feeds.items():
            if fid in ("health", "stats"):
                continue
            if body.get("ok"):
                chosen.append(fid)
            if len(chosen) >= 2:
                break

    return {
        "focus": ",".join(chosen) if chosen else "none",
        "slices": {fid: feeds[fid] for fid in chosen},
        "stats": consolidated.get("stats"),
    }