from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple, Union

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import CrawlJob, Prompt, RawResponse
from app.providers import registry
from app.schemas.crawl import CrawlJobCreate
from app.services.failure_kinds import WORKER_DIED, classify_failure

logger = logging.getLogger("geo.crawl_jobs")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_job_or_404(db: Session, job_id: int) -> CrawlJob:
    job = db.get(CrawlJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="crawl job not found")
    return job


def first_response_id(db: Session, job_id: int) -> Optional[int]:
    return db.scalar(
        select(RawResponse.id)
        .where(RawResponse.job_id == job_id)
        .order_by(RawResponse.id.asc())
        .limit(1)
    )


def job_to_out(db: Session, job: CrawlJob) -> dict:
    return {
        "id": job.id,
        "prompt_id": job.prompt_id,
        "platform": job.platform,
        "status": job.status,
        "sample_index": job.sample_index,
        "error_message": job.error_message,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "created_at": job.created_at,
        "response_id": first_response_id(db, job.id),
    }


def create_jobs(db: Session, data: CrawlJobCreate) -> List[CrawlJob]:
    platform = (data.platform or "deepseek").strip().lower()
    if not registry.is_known(platform):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"platform must be one of {list(registry.known_codes())}",
        )
    # 未接入的平台在这里就挡掉。以前放行到 worker 才 RuntimeError，
    # 用户看到的是「抓取失败」而不是「这个平台没接」—— 两者排查方向完全不同。
    crawl_mode = get_settings().crawl_mode
    if not registry.is_runnable(platform, crawl_mode=crawl_mode):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"platform '{platform}' 尚未接入（Provider 未实现），无法发起真实抓取。"
                f" 当前可用：{[c for c in registry.known_codes() if registry.is_runnable(c, crawl_mode=crawl_mode)]}"
            ),
        )
    prompt = db.get(Prompt, data.prompt_id)
    if not prompt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="prompt not found")
    if not prompt.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="prompt is inactive")

    jobs: List[CrawlJob] = []
    for i in range(1, data.samples + 1):
        job = CrawlJob(
            prompt_id=data.prompt_id,
            platform=platform,
            status="pending",
            sample_index=i,
        )
        db.add(job)
        jobs.append(job)
    db.commit()
    for job in jobs:
        db.refresh(job)
    return jobs


def list_jobs(
    db: Session,
    status_filter: Optional[str] = None,
    platform: Optional[str] = None,
    prompt_id: Optional[int] = None,
    run_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[CrawlJob], int]:
    q = select(CrawlJob).order_by(CrawlJob.id.desc())
    cq = select(func.count()).select_from(CrawlJob)
    if status_filter:
        q = q.where(CrawlJob.status == status_filter)
        cq = cq.where(CrawlJob.status == status_filter)
    if platform:
        q = q.where(CrawlJob.platform == platform)
        cq = cq.where(CrawlJob.platform == platform)
    if prompt_id is not None:
        q = q.where(CrawlJob.prompt_id == prompt_id)
        cq = cq.where(CrawlJob.prompt_id == prompt_id)
    if run_id is not None:
        q = q.where(CrawlJob.run_id == run_id)
        cq = cq.where(CrawlJob.run_id == run_id)
    total = int(db.scalar(cq) or 0)
    items = list(db.scalars(q.offset(max(offset, 0)).limit(min(limit, 200))).all())
    return items, total


def retry_job(db: Session, job_id: int) -> CrawlJob:
    job = get_job_or_404(db, job_id)
    # running 也放行：worker 容器重启后 job 会永久停在 running，
    # 原先这里拒绝重排，导致只能连库手改（见 reclaim_stuck_jobs）
    if job.status not in ("failed", "success", "running"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="only failed/success/running jobs can be re-queued",
        )
    job.status = "pending"
    job.error_message = None
    job.started_at = None
    job.finished_at = None
    db.commit()
    db.refresh(job)
    return job


def fail_job(
    db: Session,
    job: CrawlJob,
    reason: Union[BaseException, str],
    *,
    kind: Optional[str] = None,
) -> CrawlJob:
    """把一条 job 收成 ``failed``，并记下失败分类（P2-08）。

    **收拢这个函数是为 P2-34 铺路。** 失败处理原先内联在 ``process_job`` 的三个
    ``except`` 分支里；将来 crawler 不碰数据库、改走
    ``POST /v1/worker/jobs/{id}/fail``，那个端点要的是同一套逻辑。
    现在不收拢，到时候就是两份会分叉的实现。

    ``kind`` 显式传入时不再分类 —— 调用方比消息文本更清楚发生了什么
    （``reclaim_stuck_jobs`` 就是这种情况：它手里那句话是自己写的）。
    """
    message = reason if isinstance(reason, str) else str(reason)
    job.failure_kind = kind or classify_failure(reason)
    job.status = "failed"
    job.error_message = message[:500]
    job.finished_at = _utcnow()
    db.commit()
    # kind=unknown 是要盯的信号：分类没认出来的失败**不会自动重试**，
    # 而它可能正是下一个该提上来的模式。`grep kind=unknown` 就能捞
    logger.warning("job %s failed kind=%s msg=%s", job.id, job.failure_kind, message[:200])
    return job


def reclaim_stuck_jobs(db: Session, older_than_sec: int) -> List[int]:
    """把僵死在 running 的 job 收成 failed。

    worker 容器是 restart: unless-stopped，抓取中途被 OOM / Chromium 崩溃 / 重新部署
    打断时，job 已经 commit 成 running 却再没人碰它 —— 既不会被 claim（只捞 pending），
    也不会自己超时。

    收成 failed 而不是直接回 pending：反复把容器搞崩的任务不该自动无限重排，
    留给人看一眼再决定（/v1/crawl-jobs/{id}/retry）。

    **P2-16 之后这条判断仍然成立**，落点变成 ``failure_kind=worker_died``
    不在 ``RETRYABLE_KINDS`` 里 —— 自动重试会让「容器被 OOM / 家宽断电 /
    正在重新部署」这类环境问题不被发现。
    """
    cutoff = _utcnow() - timedelta(seconds=older_than_sec)
    stuck = list(
        db.scalars(
            select(CrawlJob).where(
                CrawlJob.status == "running",
                CrawlJob.started_at.is_not(None),
                CrawlJob.started_at < cutoff,
            )
        ).all()
    )
    if not stuck:
        return []
    for job in stuck:
        job.status = "failed"
        job.finished_at = _utcnow()
        job.failure_kind = WORKER_DIED
        job.error_message = (
            f"reclaimed: stuck in running for over {older_than_sec}s "
            "(worker likely died mid-crawl)"
        )
    db.commit()
    return [j.id for j in stuck]


def claim_pending_jobs(db: Session, limit: int) -> List[CrawlJob]:
    """Claim pending jobs by marking running (simple, single-worker safe enough for demo)."""
    jobs = list(
        db.scalars(
            select(CrawlJob)
            .where(CrawlJob.status == "pending")
            .order_by(CrawlJob.id.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
    )
    now = _utcnow()
    for job in jobs:
        job.status = "running"
        job.started_at = now
        job.error_message = None
    if jobs:
        db.commit()
        for job in jobs:
            db.refresh(job)
    return jobs
