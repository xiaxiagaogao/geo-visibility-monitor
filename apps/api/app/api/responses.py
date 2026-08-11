from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import (
    assert_brand_visible,
    assert_prompt_visible,
    assert_response_visible,
    assert_run_visible,
    current_principal,
    get_db,
    require_write,
    visible_brand_ids,
)
from app.core.security import Principal
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


def _resolve_scope(
    db: Session,
    principal: Principal,
    *,
    prompt_id: Optional[int],
    brand_id: Optional[int],
    run_id: Optional[int],
) -> Optional[List[int]]:
    """逐个校验显式给的归属参数，返回「还必须收敛到的品牌集合」（None = 不限）。

    ``run_id`` 和 ``prompt_id`` / ``brand_id`` 一样算收敛条件：run 下的 job 全部
    建自该 run 所属任务的品牌（services/tasks.create_run），所以 run 可见即这批
    样本可见。但**必须先 assert_run_visible** —— 少了它，客户换一个 run_id 数字
    就能列出别家的样本，而参数本身看起来完全无害。
    """
    if brand_id is not None:
        assert_brand_visible(db, principal, brand_id)
    if prompt_id is not None:
        assert_prompt_visible(db, principal, prompt_id)
    if run_id is not None:
        assert_run_visible(db, principal, run_id)
    # 一个收敛条件都没给时，客户必须被收敛到自己的品牌集合，否则默认返回全部
    if brand_id is None and prompt_id is None and run_id is None:
        return visible_brand_ids(db, principal)
    return None


def _scoped(
    stmt,
    *,
    platform: Optional[str],
    answer_status: Optional[str],
    prompt_id: Optional[int],
    brand_id: Optional[int],
    run_id: Optional[int],
    allowed_brands: Optional[List[int]],
):
    """把过滤条件拼到一个以 ``RawResponse`` 为主表的 select 上。

    **join 先算后拼，一张表只 join 一次。** 原先这里是「按条件各拼各的」：
    prompt/brand 分支拼一次 crawl_jobs，客户收敛分支再拼一次 —— 当时不撞车
    只是因为那两个分支互斥。再加一个走 crawl_jobs 的条件（run_id）就会重复
    join 同一张表，SQLAlchemy 会当成两个实例，过滤条件落在谁身上全看运气。
    """
    need_job = (
        prompt_id is not None
        or brand_id is not None
        or run_id is not None
        or allowed_brands is not None
    )
    need_prompt = brand_id is not None or allowed_brands is not None
    if need_job:
        stmt = stmt.join(CrawlJob, CrawlJob.id == RawResponse.job_id)
    if need_prompt:
        stmt = stmt.join(Prompt, Prompt.id == CrawlJob.prompt_id)

    if platform:
        stmt = stmt.where(RawResponse.platform == platform)
    if answer_status:
        stmt = stmt.where(RawResponse.answer_status == answer_status)
    if prompt_id is not None:
        stmt = stmt.where(CrawlJob.prompt_id == prompt_id)
    if run_id is not None:
        stmt = stmt.where(CrawlJob.run_id == run_id)
    if brand_id is not None:
        stmt = stmt.where(Prompt.brand_id == brand_id)
    if allowed_brands is not None:
        stmt = stmt.where(Prompt.brand_id.in_(allowed_brands))
    return stmt


@router.get("", response_model=RawResponseListOut)
def list_responses(
    platform: Optional[str] = None,
    prompt_id: Optional[int] = None,
    brand_id: Optional[int] = None,
    run_id: Optional[int] = Query(
        None, description="只看这一次运行的样本（任务详情页的样本列表用它）"
    ),
    answer_status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, description="跳过前 N 条；与 total 配合翻页"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
):
    allowed_brands = _resolve_scope(
        db, principal, prompt_id=prompt_id, brand_id=brand_id, run_id=run_id
    )
    if allowed_brands is not None and not allowed_brands:
        return RawResponseListOut(items=[], total=0)

    filters = dict(
        platform=platform,
        answer_status=answer_status,
        prompt_id=prompt_id,
        brand_id=brand_id,
        run_id=run_id,
        allowed_brands=allowed_brands,
    )
    q = _scoped(
        select(RawResponse).options(
            selectinload(RawResponse.citations),
            selectinload(RawResponse.mentions),
        ),
        **filters,
    ).order_by(RawResponse.id.desc())
    cq = _scoped(select(func.count()).select_from(RawResponse), **filters)

    total = int(db.scalar(cq) or 0)
    items = list(db.scalars(q.offset(offset).limit(limit)).all())
    return RawResponseListOut(items=[_to_out(r) for r in items], total=total)


@router.get("/{response_id}", response_model=RawResponseOut)
def get_response(
    response_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
):
    assert_response_visible(db, principal, response_id)
    row = _load_response(db, response_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="response not found")
    return _to_out(row)


@router.post("/{response_id}/annotate", response_model=RawResponseOut)
def post_annotate_one(
    response_id: int,
    db: Session = Depends(get_db),
    _: Principal = Depends(require_write),
):
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
    _: Principal = Depends(require_write),
):
    """Backfill / re-run L1 for responses missing current annotator_version."""
    ids = annotate_unannotated(db, limit=limit)
    return AnnotateBatchOut(processed=len(ids), response_ids=ids)
