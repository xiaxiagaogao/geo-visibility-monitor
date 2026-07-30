from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db
from app.models import Prompt, RawResponse
from app.schemas.crawl import (
    CitationOut,
    CrawlJobCreate,
    CrawlJobDetailOut,
    CrawlJobListOut,
    CrawlJobOut,
    RawResponseOut,
    WorkerRunOut,
)
from app.services import crawl_jobs as job_svc
from app.services.fake_worker import run_once

router = APIRouter(prefix="/v1/crawl-jobs", tags=["crawl-jobs"])


@router.get("", response_model=CrawlJobListOut)
def list_crawl_jobs(
    job_status: Optional[str] = Query(None, alias="status"),
    platform: Optional[str] = None,
    prompt_id: Optional[int] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    items, total = job_svc.list_jobs(
        db,
        status_filter=job_status,
        platform=platform,
        prompt_id=prompt_id,
        limit=limit,
    )
    return CrawlJobListOut(
        items=[CrawlJobOut(**job_svc.job_to_out(db, j)) for j in items],
        total=total,
    )


@router.post("", response_model=List[CrawlJobOut], status_code=status.HTTP_201_CREATED)
def create_crawl_jobs(body: CrawlJobCreate, db: Session = Depends(get_db)):
    jobs = job_svc.create_jobs(db, body)
    return [CrawlJobOut(**job_svc.job_to_out(db, j)) for j in jobs]


@router.post("/worker/run-once", response_model=WorkerRunOut)
def worker_run_once(
    batch_size: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Manually process pending jobs (also runs in background loop)."""
    ids = run_once(db, batch_size)
    return WorkerRunOut(processed=len(ids), job_ids=ids)


@router.get("/{job_id}", response_model=CrawlJobDetailOut)
def get_crawl_job(job_id: int, db: Session = Depends(get_db)):
    job = job_svc.get_job_or_404(db, job_id)
    prompt = db.get(Prompt, job.prompt_id)
    base = job_svc.job_to_out(db, job)
    resp = None
    rid = base.get("response_id")
    if rid:
        row = db.scalars(
            select(RawResponse)
            .where(RawResponse.id == rid)
            .options(selectinload(RawResponse.citations))
        ).first()
        if row:
            resp = RawResponseOut(
                id=row.id,
                job_id=row.job_id,
                platform=row.platform,
                prompt_text=row.prompt_text,
                full_text=row.full_text,
                html_path=row.html_path,
                screenshot_path=row.screenshot_path,
                raw_json=row.raw_json,
                latency_ms=row.latency_ms,
                created_at=row.created_at,
                citations=[CitationOut.model_validate(c) for c in row.citations],
            )
    return CrawlJobDetailOut(
        **base,
        prompt_text=prompt.text if prompt else None,
        response=resp,
    )


@router.post("/{job_id}/retry", response_model=CrawlJobOut)
def retry_crawl_job(job_id: int, db: Session = Depends(get_db)):
    job = job_svc.retry_job(db, job_id)
    return CrawlJobOut(**job_svc.job_to_out(db, job))
