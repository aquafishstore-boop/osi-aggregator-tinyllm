"""TTL-aware HTTP client for OSIRIS public read APIs."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin

import httpx

from osi_sandbox.config import Settings, get_settings
from osi_sandbox.feeds import FEEDS, FeedSpec, assert_path_allowed

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    feed_id: str
    path: str
    ok: bool
    status_code: int | None
    data: Any
    error: str | None
    fetched_at: float
    cache_ttl_hint: float | None
    elapsed_ms: float


class OsirisClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._cache: dict[str, tuple[float, FetchResult]] = {}
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> OsirisClient:
        self._client = httpx.AsyncClient(
            base_url=self.settings.osiris_base_url.rstrip("/"),
            timeout=self.settings.http_timeout_sec,
            headers={"User-Agent": self.settings.user_agent, "Accept": "application/json"},
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("OsirisClient must be used as an async context manager")
        return self._client

    def _parse_cache_ttl(self, response: httpx.Response) -> float | None:
        cc = response.headers.get("cache-control", "")
        for part in cc.split(","):
            part = part.strip().lower()
            if part.startswith("max-age="):
                try:
                    return float(part.split("=", 1)[1])
                except ValueError:
                    return None
        expires = response.headers.get("expires")
        if expires:
            try:
                exp = parsedate_to_datetime(expires).timestamp()
                return max(0.0, exp - time.time())
            except (TypeError, ValueError, OverflowError):
                return None
        return None

    async def get_path(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        feed_id: str = "custom",
        use_cache: bool = True,
    ) -> FetchResult:
        assert_path_allowed(path)
        cache_key = f"{path}?{sorted((params or {}).items())}"
        now = time.time()
        if use_cache and cache_key in self._cache:
            expires_at, cached = self._cache[cache_key]
            if now < expires_at:
                return cached

        retries = self.settings.http_max_retries
        last_error: str | None = None
        status: int | None = None
        started = time.perf_counter()

        for attempt in range(retries):
            try:
                response = await self.client.get(path, params=params)
                status = response.status_code
                if response.status_code == 429 or response.status_code >= 500:
                    last_error = f"HTTP {response.status_code}"
                    await asyncio.sleep(min(2**attempt, 8))
                    continue
                if response.status_code >= 400:
                    return FetchResult(
                        feed_id=feed_id,
                        path=path,
                        ok=False,
                        status_code=status,
                        data=None,
                        error=f"HTTP {response.status_code}: {response.text[:300]}",
                        fetched_at=now,
                        cache_ttl_hint=None,
                        elapsed_ms=(time.perf_counter() - started) * 1000,
                    )
                try:
                    data: Any = response.json()
                except ValueError:
                    data = {"_text": response.text[:2000]}
                ttl = self._parse_cache_ttl(response) or 45.0
                result = FetchResult(
                    feed_id=feed_id,
                    path=path,
                    ok=True,
                    status_code=status,
                    data=data,
                    error=None,
                    fetched_at=now,
                    cache_ttl_hint=ttl,
                    elapsed_ms=(time.perf_counter() - started) * 1000,
                )
                if use_cache:
                    self._cache[cache_key] = (now + ttl, result)
                return result
            except httpx.HTTPError as exc:
                last_error = str(exc)
                logger.warning("fetch %s attempt %s failed: %s", path, attempt + 1, exc)
                await asyncio.sleep(min(2**attempt, 8))

        return FetchResult(
            feed_id=feed_id,
            path=path,
            ok=False,
            status_code=status,
            data=None,
            error=last_error or "unknown error",
            fetched_at=now,
            cache_ttl_hint=None,
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )

    async def fetch_feed(self, feed: FeedSpec, params: dict[str, Any] | None = None) -> FetchResult:
        return await self.get_path(feed.path, params=params, feed_id=feed.id)

    async def fetch_many(
        self,
        feed_ids: list[str],
        *,
        params_by_feed: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, FetchResult]:
        params_by_feed = params_by_feed or {}
        specs = []
        for fid in feed_ids:
            if fid not in FEEDS:
                raise ValueError(f"Unknown feed: {fid}")
            specs.append(FEEDS[fid])

        async def one(spec: FeedSpec) -> tuple[str, FetchResult]:
            return spec.id, await self.fetch_feed(spec, params_by_feed.get(spec.id))

        pairs = await asyncio.gather(*(one(s) for s in specs))
        return dict(pairs)

    def absolute_url(self, path: str) -> str:
        return urljoin(self.settings.osiris_base_url.rstrip("/") + "/", path.lstrip("/"))