from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db
from app.models import CrawlJob, Prompt, RawResponse
from app.schemas.crawl import (
    CitationOut,
    MentionOut,
    RawResponseListOut,
    RawResponseOut,
)
from app.services.annotate import annotate_response, annotate_unannotated
from pydantic import BaseModel

router = APIRouter(prefix="/v1/responses", tags=["responses"])


def _to_out(row: RawResponse) -> RawResponseOut:
    return RawResponseOut(
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


def _load_response(db: Session, response_id: int) -> Optional[RawResponse]:
    return db.scalars(
        select(RawResponse)
        .where(RawResponse.id == response_id)
        .options(
            selectinload(RawResponse.citations),
            selectinload(RawResponse.mentions),
        )
    ).first()


@router.get("", response_model=RawResponseListOut)
def list_responses(
    platform: Optional[str] = None,
    prompt_id: Optional[int] = None,
    brand_id: Optional[int] = None,
    answer_status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = (
        select(RawResponse)
        .options(
            selectinload(RawResponse.citations),
            selectinload(RawResponse.mentions),
        )
        .order_by(RawResponse.id.desc())
    )
    cq = select(func.count()).select_from(RawResponse)
    if platform:
        q = q.where(RawResponse.platform == platform)
        cq = cq.where(RawResponse.platform == platform)
    if answer_status:
        q = q.where(RawResponse.answer_status == answer_status)
        cq = cq.where(RawResponse.answer_status == answer_status)
    if prompt_id is not None or brand_id is not None:
        q = q.join(CrawlJob, CrawlJob.id == RawResponse.job_id)
        cq = cq.join(CrawlJob, CrawlJob.id == RawResponse.job_id)
        if prompt_id is not None:
            q = q.where(CrawlJob.prompt_id == prompt_id)
            cq = cq.where(CrawlJob.prompt_id == prompt_id)
        if brand_id is not None:
            q = q.join(Prompt, Prompt.id == CrawlJob.prompt_id).where(
                Prompt.brand_id == brand_id
            )
            cq = cq.join(Prompt, Prompt.id == CrawlJob.prompt_id).where(
                Prompt.brand_id == brand_id
            )
    total = int(db.scalar(cq) or 0)
    items = list(db.scalars(q.limit(limit)).all())
    return RawResponseListOut(items=[_to_out(r) for r in items], total=total)


@router.get("/{response_id}", response_model=RawResponseOut)
def get_response(response_id: int, db: Session = Depends(get_db)):
    row = _load_response(db, response_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="response not found")
    return _to_out(row)


@router.post("/{response_id}/annotate", response_model=RawResponseOut)
def post_annotate_one(response_id: int, db: Session = Depends(get_db)):
    if not db.get(RawResponse, response_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="response not found")
    annotate_response(db, response_id, replace=True)
    row = _load_response(db, response_id)
    return _to_out(row)


class AnnotateBatchOut(BaseModel):
    processed: int
    response_ids: List[int]


@router.post("/annotate/run", response_model=AnnotateBatchOut)
def post_annotate_batch(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Backfill / re-run L1 for responses missing current annotator_version."""
    ids = annotate_unannotated(db, limit=limit)
    return AnnotateBatchOut(processed=len(ids), response_ids=ids)
