from __future__ import annotations

import logging
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import List, Optional
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Brand, BrandAlias, Citation, CrawlJob, Prompt, RawResponse
from app.providers.base import CrawlResult
from app.providers.deepseek_web import DeepSeekLoginRequired
from app.providers.fake import FakeProvider
from app.providers.registry import ProviderContext, build_real_provider
from app.services.annotate import annotate_response
from app.services.crawl_jobs import claim_pending_jobs, fail_job, reclaim_stuck_jobs

logger = logging.getLogger("geo.crawl_runner")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _brand_names(db: Session, brand_id: int) -> List[str]:
    brand = db.get(Brand, brand_id)
    names: List[str] = []
    if brand:
        names.append(brand.name)
        if brand.name_en:
            names.append(brand.name_en)
    aliases = list(
        db.scalars(select(BrandAlias.alias).where(BrandAlias.brand_id == brand_id)).all()
    )
    names.extend(aliases)
    seen = set()
    out = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out or ["示例品牌"]


def _build_provider(db: Session, job: CrawlJob, prompt: Prompt):
    settings = get_settings()
    mode = (settings.crawl_mode or "fake").lower()
    platform = (job.platform or "deepseek").lower()
    brands = _brand_names(db, prompt.brand_id)

    if mode == "fake" or platform == "fake":
        return FakeProvider(
            platform_label=platform if platform != "fake" else "deepseek",
            sample_index=job.sample_index or 1,
            brand_names=brands,
        )

    # real 模式：平台与 Provider 的对应关系全在 providers/registry.py。
    # 未实现的平台在那里明确报错 —— 正常情况下 create_jobs 就该先把它挡成 400，
    # 走到这里说明是历史遗留任务或直接改库造出来的。
    return build_real_provider(
        platform,
        ProviderContext(
            settings=settings,
            sample_index=job.sample_index or 1,
            brand_names=brands,
        ),
    )


def _persist_result(db: Session, job: CrawlJob, prompt: Prompt, result: CrawlResult) -> RawResponse:
    resp = RawResponse(
        job_id=job.id,
        platform=job.platform,
        prompt_text=prompt.text,
        full_text=result.full_text,
        raw_json=result.raw_json,
        latency_ms=result.latency_ms,
        screenshot_path=(Path(result.screenshot_path).name if result.screenshot_path else None),
        html_path=None,
    )
    db.add(resp)
    db.flush()
    for c in result.citations:
        domain = c.domain or (urlparse(c.url).netloc if c.url else "unknown")
        db.add(
            Citation(
                response_id=resp.id,
                cite_index=c.cite_index,
                url=c.url,
                domain=domain or "unknown",
                title=c.title,
                snippet=c.snippet,
            )
        )
    job.status = "success"
    job.finished_at = _utcnow()
    job.error_message = None
    db.commit()
    db.refresh(resp)
    try:
        annotate_response(db, resp.id, replace=True)
        db.refresh(resp)
    except Exception:
        logger.exception("L1 annotate failed response_id=%s", resp.id)
    return resp


def process_job(db: Session, job: CrawlJob) -> Optional[RawResponse]:
    prompt = db.get(Prompt, job.prompt_id)
    if not prompt:
        fail_job(db, job, "prompt missing")
        return None

    try:
        provider = _build_provider(db, job, prompt)
        settings = get_settings()
        # hard cap slightly above provider timeout so zombies cannot stick job forever
        timeout_sec = max(60, int(settings.crawl_timeout_ms / 1000) + 45)
        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(provider.search, prompt.text)
            try:
                result = fut.result(timeout=timeout_sec)
            except FuturesTimeout:
                raise RuntimeError(f"crawl timed out after {timeout_sec}s")
        return _persist_result(db, job, prompt, result)
    except DeepSeekLoginRequired as exc:
        # 单独接住只为了不打印整条 traceback —— 登录墙不是异常情况，是凭证过期，
        # 该看的是 failure_kind 而不是栈。收尾逻辑与下面完全一致
        fail_job(db, job, exc)
        return None
    except Exception as exc:
        logger.exception("job %s failed", job.id)
        fail_job(db, job, exc)
        return None


def run_once(
    db: Session, batch_size: int = 5, environment_id: Optional[int] = None
) -> List[int]:
    """``environment_id``（P2-36）由调用方（worker 循环）算好传进来 ——
    它是节流刷新的，不该每批重算一次（要探出口 IP，是次网络请求）。"""
    reclaimed = reclaim_stuck_jobs(db, get_settings().crawl_stuck_job_sec)
    if reclaimed:
        logger.warning("reclaimed stuck running jobs %s", reclaimed)

    jobs = claim_pending_jobs(db, batch_size, environment_id=environment_id)
    done: List[int] = []
    for claimed in jobs:
        job = db.get(CrawlJob, claimed.id)
        if not job or job.status != "running":
            continue
        resp = process_job(db, job)
        if resp:
            done.append(job.id)
            logger.info("crawl success job_id=%s response_id=%s", job.id, resp.id)
        else:
            logger.info("crawl finished without response job_id=%s status=%s", job.id, job.status)
    return done
