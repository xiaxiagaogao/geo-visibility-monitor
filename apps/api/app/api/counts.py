from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.counts import CountsResponse, MetricsConfigOut
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
):
    """L2 counts only — no rates. Frontend L3 divides m/n."""
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


@router.get("/v1/config/metrics", response_model=MetricsConfigOut)
def get_metrics_config():
    """口径配置下发."""
    return MetricsConfigOut(**counts_svc.metrics_config())
