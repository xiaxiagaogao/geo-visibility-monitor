from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import CrawlJob, Prompt, RawResponse
from app.schemas.crawl import ALLOWED_PLATFORMS, CrawlJobCreate


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
    if platform not in ALLOWED_PLATFORMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"platform must be one of {list(ALLOWED_PLATFORMS)}",
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
    limit: int = 50,
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
    total = int(db.scalar(cq) or 0)
    items = list(db.scalars(q.limit(min(limit, 200))).all())
    return items, total


def retry_job(db: Session, job_id: int) -> CrawlJob:
    job = get_job_or_404(db, job_id)
    if job.status not in ("failed", "success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="only failed/success jobs can be retried (re-queue)",
        )
    job.status = "pending"
    job.error_message = None
    job.started_at = None
    job.finished_at = None
    db.commit()
    db.refresh(job)
    return job


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
