"""``GET /v1/health/credentials`` —— 登录态健康度（P2-07）。

**仅超管 / 运营**（`require_write`）。客户不该看到我们的凭证状态：
那既是运维内情，也会暴露采集拓扑。

数据由 crawler 定期写进 ``crawl_credentials``（见
``services/credential_health.report_credentials``）—— api 读不到采集节点上的
``storage_state`` 文件，所以这里读的是快照，不是实时检查。
``checked_at`` 就是快照的时间戳，**它自己也是个信号**：太旧说明 crawler 没在跑。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_write
from app.core.security import Principal
from app.models import CrawlCredential, CrawlJob
from app.schemas.credentials import CredentialHealthOut, CredentialListOut
from app.services.credential_health import OK, worse_of

router = APIRouter(prefix="/v1/health", tags=["health"])


def _last_success_by_platform(db: Session) -> Dict[str, datetime]:
    """每个平台最后一次成功抓取的时间。

    这是**原计划里 P2-07 的全部内容**，现在降级成一个辅助字段 ——
    2026-08-15 的故障里它一直是「几分钟前」，因为抓取确实在成功，
    只是头几条超时、且环境不对。**它只能发现「全红」，发现不了「悄悄降级」。**
    """
    rows = db.execute(
        select(CrawlJob.platform, func.max(CrawlJob.finished_at))
        .where(CrawlJob.status == "success")
        .group_by(CrawlJob.platform)
    ).all()
    return {p: t for p, t in rows if t}


@router.get("/credentials", response_model=CredentialListOut)
def get_credential_health(
    db: Session = Depends(get_db),
    _: Principal = Depends(require_write),
):
    last_success = _last_success_by_platform(db)
    rows = list(db.scalars(select(CrawlCredential).order_by(CrawlCredential.platform)).all())

    items: List[CredentialHealthOut] = []
    overall = OK
    for r in rows:
        overall = worse_of(overall, r.status)
        items.append(
            CredentialHealthOut(
                platform=r.platform,
                status=r.status,
                node_label=r.node_label,
                issuer_region=r.issuer_region,
                waf_kind=r.waf_kind,
                cookie_count=r.cookie_count,
                cookie_names=list(r.cookie_names or []),
                earliest_expiry=r.earliest_expiry,
                file_mtime=r.file_mtime,
                issues=list(r.issues or []),
                checked_at=r.checked_at,
                last_success_at=last_success.get(r.platform),
            )
        )

    # 一条都没有 ≠ 健康。crawler 从没上报过（老版本、或压根没在跑）时
    # 报 ok 会让这个端点变成一句安慰话
    if not items:
        overall = "unreported"

    return CredentialListOut(
        overall=overall,
        items=items,
        generated_at=datetime.now(timezone.utc),
    )
