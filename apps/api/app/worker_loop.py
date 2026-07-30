from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.services.fake_worker import run_once

logger = logging.getLogger("geo.worker_loop")

_stop = threading.Event()
_thread: Optional[threading.Thread] = None


def _loop() -> None:
    settings = get_settings()
    logger.info(
        "fake worker loop started interval=%s batch=%s",
        settings.fake_worker_interval_sec,
        settings.fake_worker_batch_size,
    )
    while not _stop.is_set():
        try:
            db = SessionLocal()
            try:
                done = run_once(db, settings.fake_worker_batch_size)
                if done:
                    logger.info("processed jobs %s", done)
            finally:
                db.close()
        except Exception:  # noqa: BLE001
            logger.exception("worker loop iteration error")
        _stop.wait(settings.fake_worker_interval_sec)
    logger.info("fake worker loop stopped")


def start_worker_loop() -> None:
    global _thread
    settings = get_settings()
    if not settings.fake_worker_enabled:
        logger.info("fake worker disabled")
        return
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="geo-fake-worker", daemon=True)
    _thread.start()


def stop_worker_loop() -> None:
    _stop.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=5)
