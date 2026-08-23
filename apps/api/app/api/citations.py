"""`GET /v1/citations/domains` —— 引用域名聚合（P2-37 之后的新需求）。

**回答的问题是「哪些站正在被 AI 引用」。** 对做 GEO 运营的人来说，这比
「AI 说了什么」更可执行 —— 知道哪些站被引，才知道内容该往哪儿投。

口径与已知偏向写在 ``services/counts.domain_counts`` 的 docstring 里，
**不在这儿重复一遍**（重复的说明迟早只改一边）。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import assert_brand_visible, current_principal, get_db
from app.core.security import Principal
from app.schemas.counts import CitationDomainsOut
from app.services.counts import domain_counts

router = APIRouter(prefix="/v1/citations", tags=["citations"])


@router.get("/domains", response_model=CitationDomainsOut)
def citation_domains(
    brand_id: int = Query(..., description="监测主品牌"),
    platform: Optional[str] = None,
    prompt_id: Optional[int] = None,
    run_id: Optional[int] = Query(None, description="只看这一次运行，口径同 /v1/counts"),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> CitationDomainsOut:
    """按引用次数降序的域名榜单。

    **归属校验不能漏** —— 这个端点吃 ``brand_id``，少了它客户换个数字
    就能看到别家的引用分布（同 ``/v1/counts`` 那条）。
    """
    assert_brand_visible(db, principal, brand_id)
    return CitationDomainsOut(
        **domain_counts(
            db, brand_id=brand_id, platform=platform, prompt_id=prompt_id,
            run_id=run_id, date_from=date_from, date_to=date_to, limit=limit,
        )
    )
