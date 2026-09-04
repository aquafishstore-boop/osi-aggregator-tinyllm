from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_prompts_dir() -> Path:
    # Prefer /app/prompts in Docker; fall back to repo prompts/ next to package root.
    candidates = [
        Path(os.environ.get("PROMPTS_DIR", "")),
        Path("/app/prompts"),
        Path(__file__).resolve().parents[2] / "prompts",
        Path.cwd() / "prompts",
    ]
    for path in candidates:
        if path and path.is_dir():
            return path
    return Path("/app/prompts")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    osiris_base_url: str = Field(default="https://osirisai.live", alias="OSIRIS_BASE_URL")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen2.5:1.5b", alias="OLLAMA_MODEL")
    data_dir: Path = Field(default=Path("./data"), alias="DATA_DIR")
    poll_interval_sec: int = Field(default=120, alias="POLL_INTERVAL_SEC", ge=60)
    worker_mode: str = Field(default="schedule", alias="WORKER_MODE")
    top_n: int = Field(default=12, alias="TOP_N", ge=1, le=100)
    core_feeds: str | None = Field(default=None, alias="CORE_FEEDS")
    http_timeout_sec: float = Field(default=45.0, alias="HTTP_TIMEOUT_SEC")
    http_max_retries: int = Field(default=3, alias="HTTP_MAX_RETRIES")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8787, alias="API_PORT")
    prompts_dir: Path = Field(default_factory=_default_prompts_dir, alias="PROMPTS_DIR")
    user_agent: str = Field(
        default="osi-sandbox/0.1 (+https://osirisai.live; research)",
        alias="USER_AGENT",
    )

    def core_feed_id_list(self) -> list[str] | None:
        if not self.core_feeds:
            return None
        return [part.strip() for part in self.core_feeds.split(",") if part.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()