"""Standalone crawl worker process (Docker crawler service)."""
from __future__ import annotations

import logging
import time

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.schema import ensure_schema
from app.services.crawl_runner import run_once
from app.services.crawl_env import describe_environment, probe_exit_ip, upsert_environment
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
    # P2-36：环境 id 在两次自检之间复用。None = 还没探到（第一轮之前 /
    # 探测失败），此时 job 的 environment_id 留空 —— 「没记」比编一个准确
    env_id = None

    while True:
        db = SessionLocal()
        try:
            if settings.crawl_credential_check_sec > 0 and time.time() >= next_cred_check:
                next_cred_check = time.time() + settings.crawl_credential_check_sec
                creds = report_credentials(db, settings)
                for r in creds:
                    log = logger.warning if r["status"] != "ok" else logger.info
                    log("credential %s status=%s %s", r["platform"], r["status"], r["issues"] or "")
                # P2-36：环境指纹和登录态检查同一轮算 —— 签发地/WAF 这两维
                # 本来就是上面那次检查的产物，不必重读文件。
                # 出口 IP 要发一次网络请求，所以跟着这个节流走，不是每批都探
                cred = creds[0] if creds else {}
                env_id = upsert_environment(
                    db,
                    describe_environment(
                        settings,
                        credential_region=cred.get("issuer_region"),
                        waf_kind=cred.get("waf_kind"),
                        exit_ip=probe_exit_ip(),
                    ),
                )
            done = run_once(db, settings.fake_worker_batch_size, environment_id=env_id)
            if done:
                logger.info("processed %s", done)
        except Exception:
            logger.exception("worker iteration failed")
        finally:
            db.close()
        time.sleep(settings.fake_worker_interval_sec)


if __name__ == "__main__":
    main()
