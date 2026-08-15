"""Standalone crawl worker process (Docker crawler service)."""
from __future__ import annotations

import logging
import time

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.schema import ensure_schema
from app.services.crawl_runner import run_once
from app.services.credential_health import report_credentials

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("geo.worker_main")


def main() -> None:
    settings = get_settings()
    ensure_schema()
    logger.info(
        "crawler starting mode=%s interval=%s",
        settings.crawl_mode,
        settings.fake_worker_interval_sec,
    )
    # P2-07：第一轮立刻自检一次，之后按 crawl_credential_check_sec 节流。
    # **不等到第一次抓取失败才知道登录态有问题** —— 这次事故的形态恰恰是
    # 「抓得到，只是悄悄降级」，等失败是等不来的
    next_cred_check = 0.0

    while True:
        db = SessionLocal()
        try:
            if settings.crawl_credential_check_sec > 0 and time.time() >= next_cred_check:
                next_cred_check = time.time() + settings.crawl_credential_check_sec
                for r in report_credentials(db, settings):
                    log = logger.warning if r["status"] != "ok" else logger.info
                    log("credential %s status=%s %s", r["platform"], r["status"], r["issues"] or "")
            done = run_once(db, settings.fake_worker_batch_size)
            if done:
                logger.info("processed %s", done)
        except Exception:
            logger.exception("worker iteration failed")
        finally:
            db.close()
        time.sleep(settings.fake_worker_interval_sec)


if __name__ == "__main__":
    main()
