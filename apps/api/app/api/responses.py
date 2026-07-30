from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db
from app.models import CrawlJob, Prompt, RawResponse
from app.schemas.crawl import CitationOut, RawResponseListOut, RawResponseOut

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
        created_at=row.created_at,
        citations=[CitationOut.model_validate(c) for c in row.citations],
    )


@router.get("", response_model=RawResponseListOut)
def list_responses(
    platform: Optional[str] = None,
    prompt_id: Optional[int] = None,
    brand_id: Optional[int] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = select(RawResponse).options(selectinload(RawResponse.citations)).order_by(
        RawResponse.id.desc()
    )
    cq = select(func.count()).select_from(RawResponse)
    if platform:
        q = q.where(RawResponse.platform == platform)
        cq = cq.where(RawResponse.platform == platform)
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
    row = db.scalars(
        select(RawResponse)
        .where(RawResponse.id == response_id)
        .options(selectinload(RawResponse.citations))
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="response not found")
    return _to_out(row)
