from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_write
from app.core.security import Principal
from app.models import Citation, CrawlJob, Prompt, RawResponse
from app.schemas.crawl import CitationOut, MentionOut, RawResponseOut
from app.services.annotate import annotate_response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/v1/ingest", tags=["ingest"])


class IngestCitation(BaseModel):
    url: str
    title: Optional[str] = None
    snippet: Optional[str] = None
    domain: Optional[str] = None
    cite_index: Optional[int] = None


class IngestL0Body(BaseModel):
    prompt_id: int
    platform: str = "deepseek"
    full_text: str = Field(..., min_length=5)
    citations: List[IngestCitation] = Field(default_factory=list)
    raw_json: Optional[Dict[str, Any]] = None
    sample_index: int = 1
    latency_ms: Optional[int] = None
    source: str = "chrome_bridge"


@router.post("/l0", response_model=RawResponseOut, status_code=status.HTTP_201_CREATED)
def ingest_l0(body: IngestL0Body, db: Session = Depends(get_db),
    _: Principal = Depends(require_write),
):
    """Accept externally captured L0 (e.g. logged-in Chrome bridge) and run L1."""
    prompt = db.get(Prompt, body.prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="prompt not found")

    now = datetime.now(timezone.utc)
    job = CrawlJob(
        prompt_id=body.prompt_id,
        platform=body.platform,
        status="success",
        sample_index=body.sample_index,
        started_at=now,
        finished_at=now,
        error_message=None,
    )
    db.add(job)
    db.flush()

    raw_json = body.raw_json or {}
    raw_json.setdefault("source", body.source)

    resp = RawResponse(
        job_id=job.id,
        platform=body.platform,
        prompt_text=prompt.text,
        full_text=body.full_text,
        raw_json=raw_json,
        latency_ms=body.latency_ms,
    )
    db.add(resp)
    db.flush()

    for i, c in enumerate(body.citations, 1):
        domain = c.domain or (urlparse(c.url).netloc if c.url else "unknown")
        db.add(
            Citation(
                response_id=resp.id,
                cite_index=c.cite_index or i,
                url=c.url,
                domain=domain or "unknown",
                title=c.title,
                snippet=c.snippet,
            )
        )
    db.commit()

    annotate_response(db, resp.id, replace=True)

    row = db.scalars(
        select(RawResponse)
        .where(RawResponse.id == resp.id)
        .options(
            selectinload(RawResponse.citations),
            selectinload(RawResponse.mentions),
        )
    ).first()
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
