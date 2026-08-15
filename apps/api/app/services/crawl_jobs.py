from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple, Union

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import CrawlJob, Prompt, RawResponse
from app.providers import registry
from app.schemas.crawl import CrawlJobCreate
from app.services.failure_kinds import WORKER_DIED, classify_failure
from app.services.retry_policy import plan_next_attempt

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
        "failure_kind": job.failure_kind,
        "attempt": job.attempt,
        "next_attempt_at": job.next_attempt_at,
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
    # **手动 retry 把自动重试的计数清零，是有意的。** 人点这个按钮意味着他做了
    # 判断（换了 storage_state、平台恢复了、限流过去了）；不清零的话一条已经耗尽
    # 次数的 job 被手动重排后立刻又不享受自动重试，等于按钮只生效一半。
    # `next_attempt_at` 也清 —— 手动重排要的是「现在就排」，不是「接着等退避」
    job.attempt = None
    job.failure_kind = None
    job.next_attempt_at = None
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
    settings = get_settings()
    message = reason if isinstance(reason, str) else str(reason)
    kind = kind or classify_failure(reason)
    attempt = (job.attempt or 0) + 1  # 旧行与冷备旧 crawler 写的行都是 NULL，按 0 读
    now = _utcnow()
    retry_at = plan_next_attempt(kind=kind, attempt=attempt, settings=settings, now=now)

    job.attempt = attempt
    job.failure_kind = kind

    if retry_at is not None:
        # 退避：回 pending 等到点再被领。**不留在 running** —— 留着会被僵死回收
        # 当成「worker 死了」收成 failed，而那条路径写的 error_message
        # 会把真正的失败原因盖掉。started_at / finished_at 一并清掉，与 retry_job 一致
        job.status = "pending"
        job.started_at = None
        job.finished_at = None
        job.next_attempt_at = retry_at
        job.error_message = message[:500]
        db.commit()
        logger.warning(
            "job %s attempt %s/%s kind=%s → 退避到 %s · msg=%s",
            job.id, attempt, settings.crawl_max_attempts, kind,
            retry_at.isoformat(), message[:200],
        )
        return job

    # 终态。重试耗尽 / 这类失败不该重试 / 开关没开，都落这里
    if attempt > 1:
        # 只在真重试过时才加前缀 —— 一次就失败的 job 加「attempt 1/3」是噪声
        message = f"attempt {attempt}/{settings.crawl_max_attempts} · {kind}: {message}"
    job.status = "failed"
    job.finished_at = now
    job.next_attempt_at = None
    job.error_message = message[:500]
    db.commit()
    # kind=unknown 是要盯的信号：分类没认出来的失败**不会自动重试**，
    # 而它可能正是下一个该提上来的模式。`grep kind=unknown` 就能捞
    logger.warning("job %s failed kind=%s attempt=%s msg=%s", job.id, kind, attempt, message[:200])
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


def claim_pending_jobs(
    db: Session, limit: int, environment_id: Optional[int] = None
) -> List[CrawlJob]:
    """领一批 pending 的 job，标成 running。

    ``FOR UPDATE SKIP LOCKED`` **本来就是多 worker 安全的** —— 两个 worker
    同时领不会领到同一条。（这个 docstring 原先写「single-worker safe enough
    for demo」，低估了实现。）

    **``next_attempt_at`` 是 P2-16 的退避闸门**：正在退避的 job 状态也是
    ``pending``，靠这个时刻把它挡在门外。``NULL`` 视为立刻可领 ——
    迁移前的旧行、以及冷备那台旧代码 crawler 建的行，都是 NULL。

    ``environment_id``（P2-36）在**领取那一刻**打上 —— 那正是「这台机器接下了
    这条 job」成为事实的时刻。传 ``None``（冷备旧代码、或环境探测失败）就不打，
    留 NULL 表示「没记」，不编一个默认值盖过去。
    """
    now = _utcnow()
    jobs = list(
        db.scalars(
            select(CrawlJob)
            .where(
                CrawlJob.status == "pending",
                or_(CrawlJob.next_attempt_at.is_(None), CrawlJob.next_attempt_at <= now),
            )
            .order_by(CrawlJob.id.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
    )
    for job in jobs:
        job.status = "running"
        job.started_at = now
        # 三个字段一起清：它们描述的是「这条 job 当前为什么是失败的」，
        # 一旦重新开跑就都过期了。**`attempt` 刻意不清** ——
        # 它是累计的尝试次数，清了重试上限就形同虚设
        job.error_message = None
        job.failure_kind = None
        job.next_attempt_at = None
        if environment_id is not None:
            job.environment_id = environment_id
    if jobs:
        db.commit()
        for job in jobs:
            db.refresh(job)
    return jobs
