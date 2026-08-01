from __future__ import annotations

import logging
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from geo_metrics import match_brand, position_bucket

from app.models import (
    Brand,
    BrandAlias,
    Citation,
    CompetitorLink,
    CrawlJob,
    Mention,
    Prompt,
    RawResponse,
)

logger = logging.getLogger("geo.annotate")

# v2: match_brand 改为「最早命中」+ 长度守恒折叠，position_bucket / evidence_snippet
# 的取值随之变化 → 存量行必须重跑（POST /v1/responses/annotate/run）
ANNOTATOR_VERSION = "l1-rules-v2"

# answer_status values (denominator definition)
# - ok: counts as valid sample for rates
# - empty / too_short / error: invalid, excluded from L2 n


def classify_answer_status(full_text: str) -> str:
    """L1 quality gate for L2 denominator (answer_status=ok only)."""
    text = (full_text or "").strip()
    if not text:
        return "empty"
    if len(text) < 20:
        return "too_short"
    # Sidebar / history chrome mistaken as answer (early DeepSeek scrapes)
    head = text[:120]
    if head.startswith("开启新对话"):
        return "error"
    if "开启新对话" in text[:80] and text.count("\n") >= 6 and len(text) < 1500:
        # long rail of history titles, little prose
        if "。 " not in text[:300] and text.count("。") < 3:
            return "error"
    # Explicit fake markers should not be "ok" if any remain
    if text.startswith("【假数据"):
        return "error"
    return "ok"


def _aliases_for_brand(db: Session, brand_id: int) -> List[str]:
    brand = db.get(Brand, brand_id)
    names: List[str] = []
    if brand:
        names.append(brand.name)
        if brand.name_en:
            names.append(brand.name_en)
    aliases = list(
        db.scalars(select(BrandAlias.alias).where(BrandAlias.brand_id == brand_id)).all()
    )
    names.extend(aliases)
    seen = set()
    out = []
    for n in names:
        s = (n or "").strip()
        if not s:
            continue
        k = s.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out


def _citation_blob(db: Session, response_id: int) -> str:
    rows = db.scalars(
        select(Citation).where(Citation.response_id == response_id)
    ).all()
    parts = []
    for c in rows:
        parts.append(c.title or "")
        parts.append(c.snippet or "")
        parts.append(c.url or "")
    return "\n".join(parts)


def _evidence(body: str, offset: Optional[int], term: Optional[str], width: int = 40) -> Optional[str]:
    if offset is None or not body:
        if term and term in body:
            i = body.find(term)
            return body[max(0, i - width) : i + len(term) + width]
        return None
    return body[max(0, offset - width) : offset + width + (len(term or "") or 8)]


def target_brand_ids(db: Session, owner_brand_id: int) -> List[int]:
    """Owner brand + its competitors."""
    ids = [owner_brand_id]
    comps = list(
        db.scalars(
            select(CompetitorLink.competitor_brand_id).where(
                CompetitorLink.brand_id == owner_brand_id
            )
        ).all()
    )
    for c in comps:
        if c not in ids:
            ids.append(c)
    return ids


def annotate_response(db: Session, response_id: int, *, replace: bool = True) -> RawResponse:
    resp = db.get(RawResponse, response_id)
    if not resp:
        raise ValueError(f"response {response_id} not found")

    job = db.get(CrawlJob, resp.job_id)
    if not job:
        raise ValueError("job missing")
    prompt = db.get(Prompt, job.prompt_id)
    if not prompt:
        raise ValueError("prompt missing")

    status = classify_answer_status(resp.full_text)
    resp.answer_status = status
    resp.annotator_version = ANNOTATOR_VERSION

    if replace:
        db.execute(delete(Mention).where(Mention.response_id == response_id))

    cite_text = _citation_blob(db, response_id)
    body = resp.full_text or ""

    for bid in target_brand_ids(db, prompt.brand_id):
        aliases = _aliases_for_brand(db, bid)
        m = match_brand(body, aliases, citation_text=cite_text)
        bucket = position_bucket(body, m.offset) if m.mention_type == "body" else None
        # invalid answers: still record mention rows but status marks denominator
        db.add(
            Mention(
                response_id=response_id,
                brand_id=bid,
                mentioned=bool(m.mentioned),
                mention_type=m.mention_type,
                position_bucket=bucket,
                position_rank=None,  # rank heuristic later
                is_recommended=False,
                sentiment=None,
                sentiment_score=None,
                evidence_snippet=_evidence(body, m.offset, m.matched_term),
            )
        )

    db.commit()
    db.refresh(resp)
    logger.info(
        "annotated response_id=%s status=%s version=%s",
        response_id,
        status,
        ANNOTATOR_VERSION,
    )
    return resp


def annotate_unannotated(db: Session, limit: int = 50) -> List[int]:
    rows = list(
        db.scalars(
            select(RawResponse)
            .where(
                (RawResponse.annotator_version.is_(None))
                | (RawResponse.annotator_version != ANNOTATOR_VERSION)
            )
            .order_by(RawResponse.id.asc())
            .limit(limit)
        ).all()
    )
    done = []
    for r in rows:
        annotate_response(db, r.id, replace=True)
        done.append(r.id)
    return done
