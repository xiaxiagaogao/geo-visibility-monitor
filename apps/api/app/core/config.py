from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://geo:geo@127.0.0.1:5432/geo"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Worker loop (API process and/or crawler process)
    fake_worker_enabled: bool = True
    fake_worker_interval_sec: float = 2.0
    fake_worker_batch_size: int = 5

    # B5 crawl mode: fake | real
    crawl_mode: str = "fake"
    crawl_timeout_ms: int = 120_000
    playwright_headless: bool = True
    deepseek_storage_state: str = ""
    deepseek_user_data_dir: str = ""
    screenshot_dir: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
