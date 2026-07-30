"""Standalone crawl worker process (Docker crawler service)."""
from __future__ import annotations

import logging
import time

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.schema import ensure_schema
from app.services.crawl_runner import run_once

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
    while True:
        db = SessionLocal()
        try:
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
