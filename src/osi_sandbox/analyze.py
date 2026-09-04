"""Ollama-backed broad and fine analysis passes."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx

from osi_sandbox.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _load_prompt(prompts_dir: Path, name: str) -> str:
    path = prompts_dir / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt template missing: {path}")
    return path.read_text(encoding="utf-8")


def _render(template: str, **kwargs: str) -> str:
    out = template
    for key, value in kwargs.items():
        out = out.replace("{{" + key + "}}", value)
    return out


class OllamaAnalyzer:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def _generate(self, prompt: str) -> str:
        url = f"{self.settings.ollama_base_url.rstrip('/')}/api/generate"
        payload = {
            "model": self.settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 1024},
        }
        async with httpx.AsyncClient(timeout=180.0) as client:
            for attempt in range(5):
                try:
                    response = await client.post(url, json=payload)
                    if response.status_code == 404:
                        # Model may still be pulling
                        logger.warning("Ollama model not ready yet (404); attempt %s", attempt + 1)
                        import asyncio

                        await asyncio.sleep(5)
                        continue
                    response.raise_for_status()
                    data = response.json()
                    return (data.get("response") or "").strip() or "_No response from model._"
                except httpx.HTTPError as exc:
                    logger.warning("Ollama generate failed: %s", exc)
                    import asyncio

                    await asyncio.sleep(min(2**attempt, 10))
            return (
                "_Analysis skipped: Ollama unreachable or model not pulled. "
                f"Expected model `{self.settings.ollama_model}` at `{self.settings.ollama_base_url}`._"
            )

    async def broad(self, consolidated: dict[str, Any]) -> str:
        template = _load_prompt(self.settings.prompts_dir, "broad.md")
        context = json.dumps(consolidated, indent=2, default=str)
        # Keep context bounded for tiny models
        if len(context) > 12000:
            context = context[:12000] + "\n… [truncated]"
        prompt = _render(template, context=context, model=self.settings.ollama_model)
        return await self._generate(prompt)

    async def fine(self, fine_pack: dict[str, Any], focus: str) -> str:
        template = _load_prompt(self.settings.prompts_dir, "fine.md")
        context = json.dumps(fine_pack, indent=2, default=str)
        if len(context) > 10000:
            context = context[:10000] + "\n… [truncated]"
        prompt = _render(
            template,
            context=context,
            focus=focus,
            model=self.settings.ollama_model,
        )
        return await self._generate(prompt)