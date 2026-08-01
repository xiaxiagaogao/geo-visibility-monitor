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

    # 鉴权：空 = 不校验（仅限本机开发）。公网部署必须设置。
    # 生成：python -c "import secrets; print(secrets.token_urlsafe(32))"
    api_key: str = ""
    # QA cookie 是否只走 HTTPS（上了反代/证书后置 true）
    api_cookie_secure: bool = False

    # Worker loop (API process and/or crawler process)
    fake_worker_enabled: bool = True
    fake_worker_interval_sec: float = 2.0
    fake_worker_batch_size: int = 5

    # B5 crawl mode: fake | real
    crawl_mode: str = "fake"
    crawl_timeout_ms: int = 120_000
    # running 超过这个时长视为「worker 死了没来得及收尾」，回收成 failed。
    # 要大于 crawl_timeout_ms + process_job 的硬上限（+45s），留足余量。
    crawl_stuck_job_sec: int = 600
    playwright_headless: bool = True
    deepseek_storage_state: str = ""
    deepseek_user_data_dir: str = ""
    # 抓完即删该会话。默认开：不删则侧栏无限堆积，DOM 抓取迟早又抓到侧栏
    # （docs/18 的事故，库里已有两条 answer_status=error 的样本）
    deepseek_delete_session: bool = True
    screenshot_dir: str = "/data/screenshots"


@lru_cache
def get_settings() -> Settings:
    return Settings()
