from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import (
    assert_prompt_visible,
    assert_run_visible,
    current_principal,
    get_db,
    require_write,
    visible_brand_ids,
)
from app.core.security import Principal
from app.models import Prompt, RawResponse
from app.schemas.crawl import (
    CitationOut,
    MentionOut,
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
    run_id: Optional[int] = Query(
        None, description="只看这一次运行的采样（含没产出响应的失败 job）"
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, description="跳过前 N 条；与 total 配合翻页"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
):
    # 两个参数都是「收敛到一个可见范围」，但**各自都得校验**：
    # run_id 不校验的话，客户换个数字就能数出别家某次运行有多少采样、失败几条。
    if prompt_id is not None:
        assert_prompt_visible(db, principal, prompt_id)
    if run_id is not None:
        assert_run_visible(db, principal, run_id)
    no_narrowing = prompt_id is None and run_id is None
    if no_narrowing and visible_brand_ids(db, principal) is not None:
        # 客户不带收敛条件时不能列全部任务 —— 任务本身也泄露别家在监测什么
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="prompt_id or run_id is required for your role",
        )
    items, total = job_svc.list_jobs(
        db,
        status_filter=job_status,
        platform=platform,
        prompt_id=prompt_id,
        run_id=run_id,
        limit=limit,
        offset=offset,
    )
    return CrawlJobListOut(
        items=[CrawlJobOut(**job_svc.job_to_out(db, j)) for j in items],
        total=total,
    )


@router.post("", response_model=List[CrawlJobOut], status_code=status.HTTP_201_CREATED)
def create_crawl_jobs(
    body: CrawlJobCreate,
    db: Session = Depends(get_db),
    _: Principal = Depends(require_write),
):
    jobs = job_svc.create_jobs(db, body)
    return [CrawlJobOut(**job_svc.job_to_out(db, j)) for j in jobs]


@router.post("/worker/run-once", response_model=WorkerRunOut)
def worker_run_once(
    batch_size: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db),
    _: Principal = Depends(require_write),
):
    """Manually process pending jobs (also runs in background loop)."""
    ids = run_once(db, batch_size)
    return WorkerRunOut(processed=len(ids), job_ids=ids)


@router.get("/{job_id}", response_model=CrawlJobDetailOut)
def get_crawl_job(
    job_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
):
    job = job_svc.get_job_or_404(db, job_id)
    assert_prompt_visible(db, principal, job.prompt_id)
    prompt = db.get(Prompt, job.prompt_id)
    base = job_svc.job_to_out(db, job)
    resp = None
    rid = base.get("response_id")
    if rid:
        row = db.scalars(
            select(RawResponse)
            .where(RawResponse.id == rid)
            .options(
                selectinload(RawResponse.citations),
                selectinload(RawResponse.mentions),
            )
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
                answer_status=row.answer_status,
                annotator_version=row.annotator_version,
                created_at=row.created_at,
                citations=[CitationOut.model_validate(c) for c in row.citations],
                mentions=[MentionOut.model_validate(m) for m in row.mentions],
            )
    return CrawlJobDetailOut(
        **base,
        prompt_text=prompt.text if prompt else None,
        response=resp,
    )


@router.post("/{job_id}/retry", response_model=CrawlJobOut)
def retry_crawl_job(
    job_id: int,
    db: Session = Depends(get_db),
    _: Principal = Depends(require_write),
):
    job = job_svc.retry_job(db, job_id)
    return CrawlJobOut(**job_svc.job_to_out(db, job))
