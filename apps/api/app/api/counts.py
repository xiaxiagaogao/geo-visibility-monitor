from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import assert_brand_visible, assert_prompt_visible, current_principal, get_db
from app.core.security import Principal
from app.schemas.counts import CountsResponse
from app.services import counts as counts_svc

router = APIRouter(tags=["counts"])


@router.get("/v1/counts", response_model=CountsResponse)
def get_counts(
    brand_id: int = Query(..., description="监测主品牌 id"),
    platform: Optional[str] = Query(None),
    prompt_id: Optional[int] = Query(None),
    date_from: Optional[str] = Query(None, alias="from", description="ISO datetime"),
    date_to: Optional[str] = Query(None, alias="to", description="ISO datetime"),
    group_by: str = Query("none", description="none|day|platform|prompt"),
    include_fake: bool = Query(
        False,
        description="默认 false：排除 raw_json.source=fake* / 【假数据】样本",
    ),
    source: Optional[str] = Query(
        None,
        description="可选：只统计该 source，如 deepseek_web / chrome_bridge",
    ),
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
):
    """L2 counts only — no rates. Frontend L3 divides m/n."""
    # brand_id 是必填参数，客户改一个数字就能查别家 —— 必须逐个校验
    assert_brand_visible(db, principal, brand_id)
    if prompt_id is not None:
        assert_prompt_visible(db, principal, prompt_id)
    data = counts_svc.compute_counts(
        db,
        brand_id=brand_id,
        platform=platform,
        prompt_id=prompt_id,
        date_from=date_from,
        date_to=date_to,
        group_by=group_by,
        include_fake=include_fake,
        source=source,
    )
    return CountsResponse(**data)


# /v1/config/metrics 已移至 app/api/config.py（与 /v1/config/platforms 同处），URL 未变。
