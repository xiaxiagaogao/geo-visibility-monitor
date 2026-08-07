from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from geo_metrics import match_brand, position_bucket
from geo_metrics.mention import MentionMatch

from app.models import (
    Brand,
    BrandAlias,
    Citation,
    CompetitorLink,
    CrawlJob,
    Mention,
    Prompt,
    RawResponse,
    RunCompetitor,
)

logger = logging.getLogger("geo.annotate")

# v2: match_brand 改为「最早命中」+ 长度守恒折叠，position_bucket / evidence_snippet
#     的取值随之变化 → 存量行必须重跑（POST /v1/responses/annotate/run）
# v3: 落库 first_offset / matched_term，并按 offset 升序派生 position_rank。
#     v2 已有的字段取值**不变**，v3 只是把此前算完就丢掉的信息补上 ——
#     所以重跑是纯增量，不会动 answer_status / position_bucket / evidence_snippet。
ANNOTATOR_VERSION = "l1-rules-v3"

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


def surface_term(body: str, m: MentionMatch) -> Optional[str]:
    """落库用的 ``matched_term``：**原文里真正出现的那一段**。

    ``match_brand`` 返回的 ``matched_term`` 是**折叠后**的形式（小写），
    正文里写的是 ``Nike`` 而它给的是 ``nike``。直接落库会有两个后果：

    1. 展示「别名命中」时大小写与原文不符
    2. ``full_text[first_offset : +len(matched_term)] == matched_term``
       这条本该成立的不变量不成立，前端没法用它自检高亮有没有错位

    折叠是长度守恒的，所以按 offset 切原文一定切得准，直接取回原貌即可。
    ``citation_only`` 没有正文 offset，只能保留折叠形式（此时上面那条不变量不适用）。
    """
    term = m.matched_term
    if not term or m.offset is None:
        return term
    return body[m.offset : m.offset + len(term)] or term


def assign_position_ranks(matches: List[Tuple[int, MentionMatch]]) -> Dict[int, int]:
    """出场顺位：正文命中的品牌按首次出现位置排名（1-based）。

    **口径必须说清楚，否则会被误读成「AI 推荐的第一名」：**

    - 只有 ``mention_type=body`` 参与排名。``citation_only`` 是在引用里命中的，
      正文根本没出现，没有「出场位置」可言 → rank 为 None，不是排在最后
    - 名次**只在被监测品牌集合内**排。若回答里先提了一个我们没监测的品牌，
      我们的 rank=1 仍然是 1 —— 它的含义是「我们关心的品牌里它最先出现」，
      不是「全文第一个出现的品牌」
    - 同 offset（别名重叠等）按 brand_id 兜底排序，保证同样输入永远同样输出

    这是**位置事实**，不是推荐度。命名与展示都不要说成「首推」。
    """
    body_hits = sorted(
        (m.offset, bid)
        for bid, m in matches
        if m.mention_type == "body" and m.offset is not None
    )
    return {bid: rank for rank, (_, bid) in enumerate(body_hits, start=1)}


def target_brand_ids(
    db: Session, owner_brand_id: int, run_id: Optional[int] = None
) -> List[int]:
    """Owner brand + its competitors.

    **带 run_id 时必须读 RunCompetitor 快照,不能查当前的 CompetitorLink** ——
    与 services/counts.py 的 competitor_ids 是同一条纪律。run 建 job 时冻结的
    竞品集是 [A, B]；如果这批 job 完成前有人整体替换了品牌的竞品配置
    （PUT /v1/brands/{id}/competitors）或对失败 job 做了 retry，抽取层按
    「当时的活配置」生成 Mention 行，就会和之后 /v1/counts?run_id= 用快照
    算出的 track_ids 对不上 —— B 从「有算」悄悄变成「未算」，不报错、不可见。

    不带 run_id 是 ad-hoc job（没有 run 归属），行为不变：查当前 CompetitorLink。

    返回值第一个必须仍是 owner_brand_id（本品）——快照里只有竞品没有本品，
    不能把本品弄丢。
    """
    ids = [owner_brand_id]
    if run_id is not None:
        comps = list(
            db.scalars(
                select(RunCompetitor.competitor_brand_id).where(
                    RunCompetitor.run_id == run_id
                )
            ).all()
        )
    else:
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

    # 两趟：先把所有品牌的命中收齐，才能算出场顺位（单趟写不出跨品牌的名次）
    matches = [
        (bid, match_brand(body, _aliases_for_brand(db, bid), citation_text=cite_text))
        for bid in target_brand_ids(db, prompt.brand_id, job.run_id)
    ]
    ranks = assign_position_ranks(matches)

    for bid, m in matches:
        bucket = position_bucket(body, m.offset) if m.mention_type == "body" else None
        # invalid answers: still record mention rows but status marks denominator
        db.add(
            Mention(
                response_id=response_id,
                brand_id=bid,
                mentioned=bool(m.mentioned),
                mention_type=m.mention_type,
                position_bucket=bucket,
                position_rank=ranks.get(bid),
                is_recommended=False,
                sentiment=None,
                sentiment_score=None,
                evidence_snippet=_evidence(body, m.offset, m.matched_term),
                first_offset=m.offset,
                matched_term=surface_term(body, m),
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
