"""Feed registry: passive allowlist, deny-list for active RECON, truncation rules."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# Active / write / privileged routes — never fetched by the sandbox MVP.
DENIED_PATHS: frozenset[str] = frozenset(
    {
        "/api/scanner",
        "/api/osint/sweep",
        "/api/cctv/proxy",
        "/api/cctv/stream-status",
        "/api/proxy-tiles",
        "/api/sdk/ingest",
        "/api/github-webhook",
        "/api/ai/analyze",
        "/api/ai/briefing",
        "/api/ai/overview",
    }
)

TruncateFn = Callable[[Any, int], dict[str, Any]]


def _as_list(payload: Any, *keys: str) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    # Common nested shapes
    for value in payload.values():
        if isinstance(value, list) and value and isinstance(value[0], (dict, list)):
            return value
    return []


def _pick(item: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in keys:
        if key in item and item[key] is not None:
            out[key] = item[key]
    return out


def truncate_generic(payload: Any, top_n: int) -> dict[str, Any]:
    items = _as_list(payload, "items", "data", "results", "features", "events")
    sample = []
    for item in items[:top_n]:
        if isinstance(item, dict):
            sample.append(
                _pick(
                    item,
                    (
                        "id",
                        "name",
                        "title",
                        "mag",
                        "magnitude",
                        "severity",
                        "place",
                        "lat",
                        "lon",
                        "longitude",
                        "latitude",
                        "time",
                        "timestamp",
                        "updated",
                        "type",
                        "status",
                        "summary",
                        "description",
                        "url",
                        "country",
                        "region",
                    ),
                )
            )
        else:
            sample.append(item)
    return {
        "count": len(items) if items else (1 if payload is not None else 0),
        "sample": sample,
        "keys": list(payload.keys()) if isinstance(payload, dict) else [],
    }


def truncate_stats(payload: Any, top_n: int) -> dict[str, Any]:
    del top_n
    if isinstance(payload, dict):
        stats = payload.get("stats", payload)
        return {"stats": stats, "timestamp": payload.get("timestamp")}
    return {"stats": payload}


def truncate_health(payload: Any, top_n: int) -> dict[str, Any]:
    del top_n
    if isinstance(payload, dict):
        return {"ok": True, "body": {k: payload[k] for k in list(payload)[:20]}}
    return {"ok": True, "body": payload}


def truncate_earthquakes(payload: Any, top_n: int) -> dict[str, Any]:
    features = _as_list(payload, "features", "earthquakes", "events")
    ranked: list[dict[str, Any]] = []
    for feat in features:
        if not isinstance(feat, dict):
            continue
        props = feat.get("properties") if isinstance(feat.get("properties"), dict) else feat
        geom = feat.get("geometry") if isinstance(feat.get("geometry"), dict) else {}
        coords = geom.get("coordinates") if isinstance(geom, dict) else None
        mag = props.get("mag") or props.get("magnitude") or 0
        try:
            mag_f = float(mag)
        except (TypeError, ValueError):
            mag_f = 0.0
        ranked.append(
            {
                "mag": mag_f,
                "place": props.get("place") or props.get("title") or props.get("name"),
                "time": props.get("time") or props.get("timestamp"),
                "coords": coords[:2] if isinstance(coords, list) else None,
                "tsunami": props.get("tsunami"),
            }
        )
    ranked.sort(key=lambda x: x.get("mag") or 0, reverse=True)
    return {"count": len(features), "top": ranked[:top_n]}


def truncate_fires(payload: Any, top_n: int) -> dict[str, Any]:
    items = _as_list(payload, "fires", "features", "hotspots", "data")
    sample = []
    for item in items[:top_n]:
        if not isinstance(item, dict):
            continue
        props = item.get("properties") if isinstance(item.get("properties"), dict) else item
        sample.append(
            _pick(
                props if isinstance(props, dict) else item,
                ("bright_ti4", "frp", "confidence", "acq_date", "latitude", "longitude", "lat", "lon", "country"),
            )
        )
    return {"count": len(items), "sample": sample}


def truncate_flights(payload: Any, top_n: int) -> dict[str, Any]:
    if isinstance(payload, dict):
        commercial = payload.get("commercial_flights")
        counts: dict[str, Any] = {}
        for key, value in payload.items():
            if isinstance(value, list):
                counts[key] = len(value)
            elif isinstance(value, (int, float)):
                counts[key] = value
        if isinstance(commercial, list):
            sample = []
            for ac in commercial[:top_n]:
                if isinstance(ac, dict):
                    sample.append(
                        _pick(
                            ac,
                            ("icao24", "callsign", "origin_country", "lat", "lon", "baro_altitude", "velocity"),
                        )
                    )
            return {
                "counts": counts,
                "sample": sample,
                "total_listed": sum(v for v in counts.values() if isinstance(v, int)),
            }
        if counts:
            return {"counts": counts, "sample": []}
        return truncate_generic(payload, top_n)
    return truncate_generic(payload, top_n)


def truncate_maritime(payload: Any, top_n: int) -> dict[str, Any]:
    vessels = _as_list(payload, "vessels", "ships", "positions", "features", "ports")
    sample = []
    for item in vessels[:top_n]:
        if isinstance(item, dict):
            props = item.get("properties") if isinstance(item.get("properties"), dict) else item
            sample.append(
                _pick(
                    props if isinstance(props, dict) else item,
                    ("name", "mmsi", "shipname", "lat", "lon", "latitude", "longitude", "type", "destination", "flag"),
                )
            )
    return {"count": len(vessels), "sample": sample}


def truncate_news(payload: Any, top_n: int) -> dict[str, Any]:
    items = _as_list(payload, "news", "items", "articles", "events", "data")
    sample = []
    for item in items[:top_n]:
        if isinstance(item, dict):
            sample.append(
                _pick(item, ("title", "source", "published", "time", "timestamp", "url", "summary", "category", "region"))
            )
    return {"count": len(items), "sample": sample}


def truncate_conflicts(payload: Any, top_n: int) -> dict[str, Any]:
    items = _as_list(payload, "conflicts", "zones", "incidents", "features", "events")
    sample = []
    for item in items[:top_n]:
        if isinstance(item, dict):
            props = item.get("properties") if isinstance(item.get("properties"), dict) else item
            sample.append(
                _pick(
                    props if isinstance(props, dict) else item,
                    ("name", "title", "country", "region", "status", "severity", "summary", "lat", "lon"),
                )
            )
    return {"count": len(items), "sample": sample}


def truncate_cyber(payload: Any, top_n: int) -> dict[str, Any]:
    items = _as_list(payload, "cves", "threats", "items", "vulnerabilities", "attacks", "data")
    sample = []
    for item in items[:top_n]:
        if isinstance(item, dict):
            sample.append(
                _pick(
                    item,
                    ("id", "cve", "cve_id", "severity", "score", "title", "summary", "published", "vendor", "product"),
                )
            )
    return {"count": len(items), "sample": sample}


def truncate_markets(payload: Any, top_n: int) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return truncate_generic(payload, top_n)

    sample: list[Any] = []
    for key in ("stocks", "indices", "oil", "commodities", "crypto", "fx"):
        block = payload.get(key)
        if isinstance(block, list):
            for item in block[: max(1, top_n // 3)]:
                if isinstance(item, dict):
                    sample.append(
                        {"bucket": key, **_pick(item, ("symbol", "name", "price", "change", "pct", "currency"))}
                    )
                else:
                    sample.append({"bucket": key, "value": item})
        elif isinstance(block, dict):
            for i, (sym, quote) in enumerate(block.items()):
                if i >= max(1, top_n // 3):
                    break
                if isinstance(quote, dict):
                    sample.append(
                        {"bucket": key, "symbol": sym, **_pick(quote, ("price", "change", "pct", "name", "currency"))}
                    )
                else:
                    sample.append({"bucket": key, "symbol": sym, "value": quote})
        if len(sample) >= top_n:
            break

    return {
        "count": payload.get("count"),
        "timestamp": payload.get("timestamp"),
        "buckets": [k for k in ("stocks", "indices", "oil", "commodities", "crypto", "fx") if k in payload],
        "sample": sample[:top_n],
    }


def truncate_space_weather(payload: Any, top_n: int) -> dict[str, Any]:
    del top_n
    if isinstance(payload, dict):
        return {
            "keys": list(payload.keys())[:30],
            "summary": {
                k: payload[k]
                for k in ("kp", "kp_index", "solar_wind", "flares", "alerts", "status", "scale", "summary")
                if k in payload
            }
            or {k: payload[k] for k in list(payload)[:8]},
        }
    return {"raw_type": type(payload).__name__}


@dataclass(frozen=True)
class FeedSpec:
    id: str
    path: str
    group: str  # system | core | on_demand
    truncate: TruncateFn = field(default=truncate_generic, repr=False)
    description: str = ""


FEEDS: dict[str, FeedSpec] = {
    "health": FeedSpec("health", "/api/health", "system", truncate_health, "Liveness probe"),
    "stats": FeedSpec("stats", "/api/stats", "system", truncate_stats, "Aggregate counters"),
    "earthquakes": FeedSpec("earthquakes", "/api/earthquakes", "core", truncate_earthquakes, "USGS seismic"),
    "fires": FeedSpec("fires", "/api/fires", "core", truncate_fires, "NASA FIRMS hotspots"),
    "conflicts": FeedSpec("conflicts", "/api/conflicts", "core", truncate_conflicts, "Conflict zones"),
    "news": FeedSpec("news", "/api/news", "core", truncate_news, "OSINT news"),
    "cyber-threats": FeedSpec("cyber-threats", "/api/cyber-threats", "core", truncate_cyber, "CVE rollup"),
    "maritime": FeedSpec("maritime", "/api/maritime", "core", truncate_maritime, "Maritime traffic"),
    "flights": FeedSpec("flights", "/api/flights", "core", truncate_flights, "ADS-B aircraft"),
    "markets": FeedSpec("markets", "/api/markets", "core", truncate_markets, "Defence markets"),
    "space-weather": FeedSpec(
        "space-weather", "/api/space-weather", "core", truncate_space_weather, "NOAA SWPC"
    ),
    "region-dossier": FeedSpec(
        "region-dossier", "/api/region-dossier", "on_demand", truncate_generic, "Region composite"
    ),
    "gdelt": FeedSpec("gdelt", "/api/gdelt", "on_demand", truncate_news, "GDELT events"),
    "cyber-attacks": FeedSpec(
        "cyber-attacks", "/api/cyber-attacks", "on_demand", truncate_cyber, "Attack events"
    ),
    "osint-dns": FeedSpec("osint-dns", "/api/osint/dns", "on_demand", truncate_generic, "DNS lookup"),
    "osint-whois": FeedSpec("osint-whois", "/api/osint/whois", "on_demand", truncate_generic, "WHOIS"),
    "osint-certs": FeedSpec("osint-certs", "/api/osint/certs", "on_demand", truncate_generic, "CT certs"),
    "osint-ip": FeedSpec("osint-ip", "/api/osint/ip", "on_demand", truncate_generic, "IP enrichment"),
    "osint-cve": FeedSpec("osint-cve", "/api/osint/cve", "on_demand", truncate_cyber, "NVD CVE"),
    "osint-sanctions": FeedSpec(
        "osint-sanctions", "/api/osint/sanctions", "on_demand", truncate_generic, "Sanctions search"
    ),
}

CORE_FEED_IDS: tuple[str, ...] = tuple(f.id for f in FEEDS.values() if f.group == "core")
SYSTEM_FEED_IDS: tuple[str, ...] = tuple(f.id for f in FEEDS.values() if f.group == "system")


def assert_path_allowed(path: str) -> None:
    normalized = path.split("?", 1)[0].rstrip("/") or path
    for denied in DENIED_PATHS:
        if normalized == denied or normalized.startswith(denied + "/"):
            raise PermissionError(f"Path denied by sandbox policy: {path}")


def resolve_core_ids(override: list[str] | None = None) -> list[str]:
    if override:
        unknown = [fid for fid in override if fid not in FEEDS]
        if unknown:
            raise ValueError(f"Unknown feed ids: {unknown}")
        for fid in override:
            assert_path_allowed(FEEDS[fid].path)
        return list(override)
    return list(CORE_FEED_IDS)