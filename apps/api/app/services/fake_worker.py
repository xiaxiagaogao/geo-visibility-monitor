from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Brand, BrandAlias, Citation, CrawlJob, Prompt, RawResponse
from app.services.crawl_jobs import claim_pending_jobs
from app.services.annotate import annotate_response

logger = logging.getLogger("geo.fake_worker")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _brand_names(db: Session, brand_id: int) -> List[str]:
    brand = db.get(Brand, brand_id)
    names: List[str] = []
    if brand:
        names.append(brand.name)
        if brand.name_en:
            names.append(brand.name_en)
    aliases = db.scalars(
        select(BrandAlias.alias).where(BrandAlias.brand_id == brand_id)
    ).all()
    names.extend(list(aliases))
    # unique preserve order
    seen = set()
    out = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out or ["示例品牌"]


def build_fake_l0(platform: str, prompt_text: str, brand_names: List[str], sample_index: int) -> dict:
    """Generate fake L0 payload — no browser. Deterministic-ish for demo."""
    primary = brand_names[0]
    # alternate mention / no-mention for multi-sample feel
    mention = sample_index % 2 == 1
    if mention:
        full_text = (
            f"【假数据·{platform}】关于「{prompt_text}」。\n\n"
            f"综合来看，{primary} 是不少用户会提到的选择之一。"
            f"也有人会对比其他平台，但本条样本重点覆盖 {primary}。\n\n"
            f"（B3 fake worker 生成，非真实大模型回答。sample_index={sample_index}）"
        )
    else:
        full_text = (
            f"【假数据·{platform}】关于「{prompt_text}」。\n\n"
            f"市场上有多家可选方案，需要结合预算与口碑综合判断。"
            f"本条样本故意不写具体品牌名，便于后续对比标注。\n\n"
            f"（B3 fake worker 生成，非真实大模型回答。sample_index={sample_index}）"
        )

    citations = [
        {
            "cite_index": 1,
            "url": f"https://example.com/geo-fake/{platform}/article-1",
            "domain": "example.com",
            "title": f"假引用：{primary}相关讨论" if mention else "假引用：行业综述",
            "snippet": f"与问题「{prompt_text[:40]}」相关的示意摘要。",
        },
        {
            "cite_index": 2,
            "url": "https://news.example.org/home-renovation-guide",
            "domain": "news.example.org",
            "title": "家装选购指南（示意）",
            "snippet": "占位引用，用于 L0 citations 管道验证。",
        },
    ]
    raw_json = {
        "source": "fake_worker",
        "platform": platform,
        "mention_intended": mention,
        "brand_names": brand_names,
        "sample_index": sample_index,
    }
    return {
        "full_text": full_text,
        "citations": citations,
        "raw_json": raw_json,
        "latency_ms": 50 + sample_index * 3,
    }


def process_job(db: Session, job: CrawlJob) -> RawResponse:
    prompt = db.get(Prompt, job.prompt_id)
    if not prompt:
        job.status = "failed"
        job.error_message = "prompt missing"
        job.finished_at = _utcnow()
        db.commit()
        raise RuntimeError(job.error_message)

    brand_names = _brand_names(db, prompt.brand_id)
    payload = build_fake_l0(job.platform, prompt.text, brand_names, job.sample_index)

    resp = RawResponse(
        job_id=job.id,
        platform=job.platform,
        prompt_text=prompt.text,
        full_text=payload["full_text"],
        raw_json=payload["raw_json"],
        latency_ms=payload["latency_ms"],
        screenshot_path=None,
        html_path=None,
    )
    db.add(resp)
    db.flush()

    for c in payload["citations"]:
        db.add(
            Citation(
                response_id=resp.id,
                cite_index=c.get("cite_index"),
                url=c["url"],
                domain=c["domain"],
                title=c.get("title"),
                snippet=c.get("snippet"),
            )
        )

    job.status = "success"
    job.finished_at = _utcnow()
    job.error_message = None
    db.commit()
    db.refresh(resp)
    # B4: L1 annotation (rules)
    try:
        annotate_response(db, resp.id, replace=True)
        db.refresh(resp)
    except Exception:
        logger.exception("L1 annotate failed response_id=%s", resp.id)
    return resp


def run_once(db: Session, batch_size: int = 5) -> List[int]:
    jobs = claim_pending_jobs(db, batch_size)
    done: List[int] = []
    for job in jobs:
        # re-bind job in this session state after commit in claim
        job = db.get(CrawlJob, job.id)
        if not job or job.status != "running":
            continue
        try:
            process_job(db, job)
            done.append(job.id)
            logger.info("fake_worker success job_id=%s", job.id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("fake_worker failed job_id=%s", job.id)
            job = db.get(CrawlJob, job.id)
            if job:
                job.status = "failed"
                job.error_message = str(exc)[:500]
                job.finished_at = _utcnow()
                db.commit()
    return done
