from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db
from app.models import Brand, CrawlJob, Mention, Prompt, RawResponse
from app.services.counts import compute_counts

router = APIRouter(tags=["qa"])

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


@router.get("/qa", response_class=HTMLResponse)
def qa_home(request: Request, db: Session = Depends(get_db)):
    job_rows = db.execute(
        select(CrawlJob.status, func.count()).group_by(CrawlJob.status)
    ).all()
    job_by_status = {s: c for s, c in job_rows}

    status_rows = db.execute(
        select(RawResponse.answer_status, func.count()).group_by(RawResponse.answer_status)
    ).all()
    answer_by_status = {(s or "null"): c for s, c in status_rows}

    n_responses = int(db.scalar(select(func.count()).select_from(RawResponse)) or 0)
    n_mentions = int(db.scalar(select(func.count()).select_from(Mention)) or 0)
    n_brands = int(db.scalar(select(func.count()).select_from(Brand)) or 0)
    n_prompts = int(db.scalar(select(func.count()).select_from(Prompt)) or 0)

    recent_jobs = list(
        db.scalars(select(CrawlJob).order_by(desc(CrawlJob.id)).limit(10)).all()
    )
    recent_responses = list(
        db.scalars(
            select(RawResponse)
            .options(selectinload(RawResponse.mentions))
            .order_by(desc(RawResponse.id))
            .limit(10)
        ).all()
    )

    # counts for brand 1 if exists
    brand1 = db.get(Brand, 1)
    counts = None
    if brand1:
        try:
            counts = compute_counts(db, brand_id=1)
        except Exception:
            counts = None

    return templates.TemplateResponse(
        request,
        "qa/home.html",
        {
            "job_by_status": job_by_status,
            "answer_by_status": answer_by_status,
            "n_responses": n_responses,
            "n_mentions": n_mentions,
            "n_brands": n_brands,
            "n_prompts": n_prompts,
            "recent_jobs": recent_jobs,
            "recent_responses": recent_responses,
            "counts": counts,
            "brand1": brand1,
        },
    )


@router.get("/qa/jobs", response_class=HTMLResponse)
def qa_jobs(
    request: Request,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = select(CrawlJob).order_by(desc(CrawlJob.id))
    if status:
        q = q.where(CrawlJob.status == status)
    jobs = list(db.scalars(q.limit(limit)).all())
    # attach prompt text
    prompt_ids = list({j.prompt_id for j in jobs})
    prompts = {}
    if prompt_ids:
        for p in db.scalars(select(Prompt).where(Prompt.id.in_(prompt_ids))).all():
            prompts[p.id] = p
    return templates.TemplateResponse(
        request,
        "qa/jobs.html",
        {
            "jobs": jobs,
            "prompts": prompts,
            "status": status,
        },
    )


@router.get("/qa/responses", response_class=HTMLResponse)
def qa_responses(
    request: Request,
    answer_status: Optional[str] = None,
    platform: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = (
        select(RawResponse)
        .options(selectinload(RawResponse.mentions), selectinload(RawResponse.citations))
        .order_by(desc(RawResponse.id))
    )
    if answer_status:
        q = q.where(RawResponse.answer_status == answer_status)
    if platform:
        q = q.where(RawResponse.platform == platform)
    rows = list(db.scalars(q.limit(limit)).all())
    return templates.TemplateResponse(
        request,
        "qa/responses.html",
        {
            "rows": rows,
            "answer_status": answer_status,
            "platform": platform,
        },
    )


@router.get("/qa/responses/{response_id}", response_class=HTMLResponse)
def qa_response_detail(
    request: Request, response_id: int, db: Session = Depends(get_db)
):
    row = db.scalars(
        select(RawResponse)
        .where(RawResponse.id == response_id)
        .options(
            selectinload(RawResponse.mentions),
            selectinload(RawResponse.citations),
        )
    ).first()
    brands = {
        b.id: b for b in db.scalars(select(Brand)).all()
    }
    job = db.get(CrawlJob, row.job_id) if row else None
    prompt = db.get(Prompt, job.prompt_id) if job else None
    screenshot_url = None
    display_raw = None
    if row:
        display_raw = dict(row.raw_json or {})
        # never surface conversation URLs in QA
        for k in list(display_raw.keys()):
            if "url" in k.lower() or "chat" in k.lower():
                if isinstance(display_raw.get(k), str) and "deepseek.com" in display_raw[k]:
                    display_raw[k] = "[redacted-conversation-url]"
        if row.screenshot_path:
            name = Path(row.screenshot_path).name
            screenshot_url = f"/qa/media/screenshots/{name}"
    return templates.TemplateResponse(
        request,
        "qa/response_detail.html",
        {
            "row": row,
            "job": job,
            "prompt": prompt,
            "brands": brands,
            "screenshot_url": screenshot_url,
            "display_raw_json": display_raw,
        },
    )
