from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CompetitorLink, CrawlJob, Mention, Prompt, RawResponse
from app.services.annotate import ANNOTATOR_VERSION
from app.services.brands import get_brand_or_404


_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_dt(value: Optional[str], *, end: bool = False) -> Optional[datetime]:
    """解析 ISO 时间；``end=True`` 时纯日期补到当天最后一刻。

    区间是闭区间（created_at <= to）。若 ``to=2026-08-01`` 按 00:00:00 处理，
    整个 8/1 都会被排除 —— 前端传日期而非时间戳时必踩。
    """
    if not value:
        return None
    v = value.strip()
    date_only = bool(_DATE_ONLY.match(v))
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(v)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid datetime: {value}",
        ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if end and date_only:
        dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    return dt


def _empty_brand_counts(brand_id: int) -> Dict[str, int]:
    return {
        "brand_id": brand_id,
        "m_mentioned": 0,
        "m_body": 0,
        "m_citation_only": 0,
        "m_none": 0,
        "m_head": 0,
        "m_middle": 0,
        "m_tail": 0,
    }


def _empty_den() -> Dict[str, int]:
    return {
        "n_valid": 0,
        "n_total_responses": 0,
        "n_empty": 0,
        "n_too_short": 0,
        "n_error": 0,
        "n_unannotated": 0,
    }



FAKE_SOURCES = frozenset({"fake_worker", "fake_provider", "fake", "fake_provider_v1"})


def is_fake_response(resp: RawResponse) -> bool:
    """Historical B3 fake L0 rows — excluded from L2 by default."""
    raw = resp.raw_json if isinstance(resp.raw_json, dict) else {}
    src = str(raw.get("source") or "").strip().lower()
    if src.startswith("fake") or src in FAKE_SOURCES:
        return True
    text = (resp.full_text or "").lstrip()
    if text.startswith("【假数据"):
        return True
    return False


def competitor_ids(db: Session, brand_id: int) -> List[int]:
    return list(
        db.scalars(
            select(CompetitorLink.competitor_brand_id).where(
                CompetitorLink.brand_id == brand_id
            )
        ).all()
    )


def _base_response_query(
    db: Session,
    *,
    brand_id: int,
    platform: Optional[str],
    prompt_id: Optional[int],
    dt_from: Optional[datetime],
    dt_to: Optional[datetime],
):
    """Responses tied to prompts of this brand (owner brand's monitoring set)."""
    q = (
        select(RawResponse)
        .join(CrawlJob, CrawlJob.id == RawResponse.job_id)
        .join(Prompt, Prompt.id == CrawlJob.prompt_id)
        .where(Prompt.brand_id == brand_id)
    )
    if platform:
        q = q.where(RawResponse.platform == platform)
    if prompt_id is not None:
        q = q.where(CrawlJob.prompt_id == prompt_id)
    if dt_from is not None:
        q = q.where(RawResponse.created_at >= dt_from)
    if dt_to is not None:
        q = q.where(RawResponse.created_at <= dt_to)
    return q


def _accumulate_denominator(den: Dict[str, int], status: Optional[str]) -> None:
    den["n_total_responses"] += 1
    if status == "ok":
        den["n_valid"] += 1
    elif status == "empty":
        den["n_empty"] += 1
    elif status == "too_short":
        den["n_too_short"] += 1
    elif status == "error":
        den["n_error"] += 1
    elif status is None:
        den["n_unannotated"] += 1


def _accumulate_mention(bc: Dict[str, int], m: Mention) -> None:
    if m.mentioned:
        bc["m_mentioned"] += 1
    mt = m.mention_type or "none"
    if mt == "body":
        bc["m_body"] += 1
    elif mt == "citation_only":
        bc["m_citation_only"] += 1
    else:
        bc["m_none"] += 1
    pb = m.position_bucket
    if pb == "head":
        bc["m_head"] += 1
    elif pb == "middle":
        bc["m_middle"] += 1
    elif pb == "tail":
        bc["m_tail"] += 1


def _bucket_key(resp: RawResponse, group_by: str, prompt_id_by_job: Dict[int, int]) -> str:
    if group_by == "none":
        return "all"
    if group_by == "day":
        # UTC day
        dt = resp.created_at
        if dt is None:
            return "unknown"
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).date().isoformat()
    if group_by == "platform":
        return resp.platform or "unknown"
    if group_by == "prompt":
        return str(prompt_id_by_job.get(resp.job_id, "unknown"))
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="group_by must be one of: none, day, platform, prompt",
    )


def compute_counts(
    db: Session,
    *,
    brand_id: int,
    platform: Optional[str] = None,
    prompt_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    group_by: str = "none",
    include_fake: bool = False,
    source: Optional[str] = None,
) -> dict:
    get_brand_or_404(db, brand_id)
    group_by = (group_by or "none").lower()
    if group_by not in ("none", "day", "platform", "prompt"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="group_by must be one of: none, day, platform, prompt",
        )

    dt_from = _parse_dt(date_from)
    dt_to = _parse_dt(date_to, end=True)
    comp_ids = competitor_ids(db, brand_id)
    track_ids = [brand_id] + [c for c in comp_ids if c != brand_id]

    responses = list(
        db.scalars(
            _base_response_query(
                db,
                brand_id=brand_id,
                platform=platform,
                prompt_id=prompt_id,
                dt_from=dt_from,
                dt_to=dt_to,
            ).order_by(RawResponse.id.asc())
        ).all()
    )
    if not include_fake:
        responses = [r for r in responses if not is_fake_response(r)]
    if source:
        src_l = source.strip().lower()
        def _src(r: RawResponse) -> str:
            raw = r.raw_json if isinstance(r.raw_json, dict) else {}
            return str(raw.get("source") or "").strip().lower()
        responses = [r for r in responses if _src(r) == src_l]
    resp_ids = [r.id for r in responses]
    job_ids = list({r.job_id for r in responses})
    prompt_id_by_job: Dict[int, int] = {}
    if job_ids:
        rows = db.execute(
            select(CrawlJob.id, CrawlJob.prompt_id).where(CrawlJob.id.in_(job_ids))
        ).all()
        prompt_id_by_job = {jid: pid for jid, pid in rows}

    mentions_by_resp: Dict[int, List[Mention]] = defaultdict(list)
    if resp_ids:
        ments = list(
            db.scalars(
                select(Mention).where(
                    Mention.response_id.in_(resp_ids),
                    Mention.brand_id.in_(track_ids),
                )
            ).all()
        )
        for m in ments:
            mentions_by_resp[m.response_id].append(m)

    # overall
    overall_den = _empty_den()
    overall_brand = {bid: _empty_brand_counts(bid) for bid in track_ids}

    # series buckets
    series_den: Dict[str, Dict[str, int]] = defaultdict(_empty_den)
    series_brand: Dict[str, Dict[int, Dict[str, int]]] = defaultdict(
        lambda: {bid: _empty_brand_counts(bid) for bid in track_ids}
    )

    for resp in responses:
        key = _bucket_key(resp, group_by, prompt_id_by_job)
        _accumulate_denominator(overall_den, resp.answer_status)
        if group_by != "none":
            _accumulate_denominator(series_den[key], resp.answer_status)

        # only count mentions toward brand metrics when sample is valid
        if resp.answer_status != "ok":
            continue

        for m in mentions_by_resp.get(resp.id, []):
            if m.brand_id not in overall_brand:
                continue
            _accumulate_mention(overall_brand[m.brand_id], m)
            if group_by != "none":
                _accumulate_mention(series_brand[key][m.brand_id], m)

    def pack_den(d: Dict[str, int]) -> dict:
        return {
            "definition": "answer_status=ok",
            **d,
        }

    def pack_brand(bc: Dict[str, int]) -> dict:
        return dict(bc)

    series = []
    if group_by != "none":
        for key in sorted(series_den.keys()):
            series.append(
                {
                    "key": key,
                    "denominator": pack_den(series_den[key]),
                    "brand": pack_brand(series_brand[key][brand_id]),
                    "competitors": [
                        pack_brand(series_brand[key][cid]) for cid in comp_ids
                    ],
                }
            )

    return {
        "brand_id": brand_id,
        "filters": {
            "platform": platform,
            "prompt_id": prompt_id,
            "from": date_from,
            "to": date_to,
            "include_fake": include_fake,
            "source": source,
        },
        "group_by": group_by,
        "denominator": pack_den(overall_den),
        "brand": pack_brand(overall_brand[brand_id]),
        "competitors": [pack_brand(overall_brand[cid]) for cid in comp_ids],
        "series": series,
        "note": "counts only; compute rates on client (L3); fake L0 excluded unless include_fake=true",
    }


def metrics_config() -> dict:
    return {
        "answer_status_values": ["ok", "empty", "too_short", "error"],
        "valid_denominator": "answer_status=ok",
        "mention_types": ["body", "citation_only", "none"],
        "position_buckets": ["head", "middle", "tail"],
        "default_composite_weights": {
            "mention": 0.4,
            "position": 0.3,
            "sentiment": 0.3,
        },
        "annotator_version": ANNOTATOR_VERSION,
        "crawl_mode_default_hint": "fake|real",
    }
