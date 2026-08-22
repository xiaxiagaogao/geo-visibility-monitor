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
from app.models import CrawlJob, Mention, Prompt, RawResponse
from app.schemas.crawl import (
    CitationOut,
    MentionOut,
    RawResponseListOut,
    RawResponseOut,
    RawResponseSummaryListOut,
    RawResponseSummaryOut,
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
        search_used=row.search_used,
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


#: 列表里每条正文只带这么多字。够看出「这条在讲什么」，又不至于把整页拖成几百 KB。
PREVIEW_CHARS = 160


def _summary_columns():
    """轻量投影选的列。**这里没有 full_text 和 raw_json** ——

    正文只以 substr 出来的前 ``PREVIEW_CHARS`` 字 + 总长度两个派生值出现，
    截断发生在数据库那侧：大列既不进 Python 也不过网。
    """
    return (
        RawResponse.id,
        RawResponse.job_id,
        RawResponse.platform,
        RawResponse.prompt_text,
        func.substr(RawResponse.full_text, 1, PREVIEW_CHARS).label("text_preview"),
        func.length(RawResponse.full_text).label("text_length"),
        RawResponse.screenshot_path,
        RawResponse.latency_ms,
        RawResponse.answer_status,
        RawResponse.annotator_version,
        # P2-37 联网标注。**加在这里而不是只加在 out 模型上** —— 这个投影是
        # 显式列清单，漏一列不会报错，只会在构造 out 时 AttributeError
        RawResponse.search_used,
        RawResponse.created_at,
    )


@router.get("/summary", response_model=RawResponseSummaryListOut)
def list_response_summaries(
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
    """列表用的轻量投影。过滤参数与 ``GET /v1/responses`` 完全一致。

    **为什么单开一个端点：** 列表页要的是 prompt_text / 平台 / 状态 / 本品命中，
    而 ``/v1/responses`` 每行都拖着完整 ``full_text`` 和 ``raw_json``
    （raw_json 里往往还有一份同样的正文）。一页 20 条就能到几百 KB，
    而其中 99% 的字节在列表上一个像素都不渲染。

    这里 select 的是列不是 ORM 实体：大列在数据库那侧就被 substr 掉了，
    既不进 Python 也不过网。

    路由声明必须在 ``/{response_id}`` 之前 —— FastAPI 按声明顺序匹配，
    反过来的话 ``/summary`` 会被当成 response_id 去解析，得到一个 422。
    """
    allowed_brands = _resolve_scope(
        db, principal, prompt_id=prompt_id, brand_id=brand_id, run_id=run_id
    )
    if allowed_brands is not None and not allowed_brands:
        return RawResponseSummaryListOut(items=[], total=0)

    filters = dict(
        platform=platform,
        answer_status=answer_status,
        prompt_id=prompt_id,
        brand_id=brand_id,
        run_id=run_id,
        allowed_brands=allowed_brands,
    )
    q = (
        _scoped(select(*_summary_columns()), **filters)
        .order_by(RawResponse.id.desc())
        .offset(offset)
        .limit(limit)
    )
    cq = _scoped(select(func.count()).select_from(RawResponse), **filters)

    total = int(db.scalar(cq) or 0)
    rows = list(db.execute(q).all())

    # 标注单独取：一次 IN 查询把这一页的全取回来，避免 N 次子查询
    by_response: dict = {}
    if rows:
        mentions = db.scalars(
            select(Mention)
            .where(Mention.response_id.in_([r.id for r in rows]))
            .order_by(Mention.id)
        ).all()
        for m in mentions:
            by_response.setdefault(m.response_id, []).append(m)

    return RawResponseSummaryListOut(
        items=[
            RawResponseSummaryOut(
                id=r.id,
                job_id=r.job_id,
                platform=r.platform,
                prompt_text=r.prompt_text,
                text_preview=r.text_preview,
                text_length=r.text_length,
                screenshot_path=r.screenshot_path,
                latency_ms=r.latency_ms,
                answer_status=r.answer_status,
                annotator_version=r.annotator_version,
                search_used=r.search_used,
                created_at=r.created_at,
                mentions=[
                    MentionOut.model_validate(m) for m in by_response.get(r.id, [])
                ],
            )
            for r in rows
        ],
        total=total,
    )


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
