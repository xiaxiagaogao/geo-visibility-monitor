"""采集节点用的端点（P2-34）。

## 为什么单开一个前缀

采集节点现在**直连数据库**（`DATABASE_URL` 走 tailnet 到 VPS 的 postgres）。
那条链路带来两笔债：库凭证要放在一台大陆家宽的机器上，而截图写在节点本地、
VPS 上的 api 读不到（所以 `SCREENSHOT_DIR` 一直是空的，证据页没有截图按钮）。

这个 router 是那条链路的替代：节点只出站 HTTPS，领 job、回传结果都走这里。

## 鉴权：复用现有 `X-API-Key`（2026-08-18 拍板）

**代价要写清楚**：`X-API-Key` 过中间件之后是 `Principal(kind="machine")`，
而它折算成 **superadmin**（`core/security.py`）。所以采集节点持有的是一把
**超管等价凭证** —— 换掉数据库口令并没有缩小权限面，只是换了一种形态。

因此 P2-34 的收益要按实际的说：**只走 HTTPS 出站 · 截图能随结果回来 ·
天然支持多节点**。「让节点只拿最小权限」不在其中，那需要另发一把 key。

## 只加不改

隧道模式（节点直连数据库跑 `worker_main.py`）**保持能用**，两种模式并存。
回滚 = 让节点回到旧模式，不必动代码（`PHASE2.md` §6 规矩 1）。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_write
from app.core.security import Principal
from app.schemas.crawl import WorkerLeaseItem, WorkerLeaseOut
from app.services import crawl_jobs as job_svc

router = APIRouter(prefix="/v1/worker", tags=["worker"])


@router.post("/lease", response_model=WorkerLeaseOut)
def lease_jobs(
    batch_size: int = Query(1, ge=1, le=50, description="一次最多领几条"),
    environment_id: Optional[int] = Query(
        None,
        description=(
            "P2-36 采集环境 id，由节点先 POST /v1/worker/environment 换取。"
            "不传就不打标记 —— 留 NULL 表示「没记」，比编一个准确"
        ),
    ),
    db: Session = Depends(get_db),
    _: Principal = Depends(require_write),
) -> WorkerLeaseOut:
    """领一批 job，并在**领取那一刻**标 ``running``。

    **是 POST 不是 GET**（交接文档里写的是 GET，这里按本仓的红线改了）。
    领取会改状态，而中间件对安全方法认 `geo_qa_key` Cookie —— 做成 GET
    等于开了一个跨站就能打的口子：诱导浏览器发一发，一批 job 就被标成
    ``running`` 空转到 600 秒后被僵死回收，攻击方连响应都不用读。
    `test_worker_lease.py::test_lease_cannot_be_driven_by_cookie_alone` 钉着这条。
    """
    return WorkerLeaseOut(
        jobs=[
            WorkerLeaseItem(**item)
            for item in job_svc.lease_jobs(db, batch_size, environment_id=environment_id)
        ]
    )
