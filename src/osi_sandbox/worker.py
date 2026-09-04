"""Scheduled or one-shot worker entrypoint."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from osi_sandbox.config import get_settings
from osi_sandbox.pipeline import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("osi_sandbox.worker")


async def _loop() -> None:
    settings = get_settings()
    mode = "full"
    while True:
        logger.info(
            "Starting scheduled run (interval=%ss, base=%s)",
            settings.poll_interval_sec,
            settings.osiris_base_url,
        )
        try:
            result = await run_pipeline(mode=mode, settings=settings)
            logger.info("Run complete: %s", result["run_id"])
        except Exception:
            logger.exception("Scheduled run failed")
        await asyncio.sleep(settings.poll_interval_sec)


async def _once(mode: str, focus: str | None) -> int:
    settings = get_settings()
    result = await run_pipeline(mode=mode, focus=focus, settings=settings)  # type: ignore[arg-type]
    logger.info("One-shot complete: %s", result["run_id"])
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="OSIRIS sandbox worker")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single pipeline then exit",
    )
    parser.add_argument(
        "--mode",
        choices=("ingest", "broad", "full"),
        default="full",
        help="Pipeline mode (default: full)",
    )
    parser.add_argument(
        "--focus",
        default=None,
        help="Fine-pass focus feed id (e.g. earthquakes)",
    )
    args = parser.parse_args(argv)
    settings = get_settings()

    if args.once or settings.worker_mode == "once":
        raise SystemExit(asyncio.run(_once(args.mode, args.focus)))

    asyncio.run(_loop())


if __name__ == "__main__":
    main(sys.argv[1:])