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

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_write
from app.core.config import get_settings
from app.core.security import Principal
from app.schemas.crawl import (
    CrawlJobOut,
    WorkerCredentialsIn,
    WorkerCredentialsOut,
    WorkerEnvironmentIn,
    WorkerEnvironmentOut,
    WorkerFailIn,
    WorkerLeaseItem,
    WorkerLeaseOut,
    WorkerResultIn,
    WorkerResultOut,
)
from app.services import crawl_jobs as job_svc
from app.services import worker_intake

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


def _read_screenshot(upload: UploadFile) -> bytes:
    """读出截图并当场校验。**两条都不能省：**

    - **上限**：没有的话一个跑飞的节点就能把 VPS 的盘写满，而那块盘上还有数据库。
      多读一个字节来判断「超了没有」，不把整个流吃进内存再量。
    - **魔数**：按字节判是不是 PNG，**不信 ``content-type``** —— 那是节点随口说的，
      而这个文件会以 ``.png`` 结尾被端回给浏览器。
    """
    limit = get_settings().screenshot_max_bytes
    data = upload.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            # 写字面量 413：本机 venv（py3.9）还没有 HTTP_413_CONTENT_TOO_LARGE，
            # 而 api 容器（py3.12）已经把 HTTP_413_REQUEST_ENTITY_TOO_LARGE 标了弃用。
            # 两边都能跑的只有这个数
            status_code=413,
            detail=f"screenshot exceeds SCREENSHOT_MAX_BYTES ({limit})",
        )
    if not data.startswith(worker_intake.PNG_MAGIC):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="screenshot must be a PNG (magic bytes checked, not content-type)",
        )
    return data


@router.post("/jobs/{job_id}/result", response_model=WorkerResultOut)
def report_result(
    job_id: int,
    payload: str = Form(..., description="WorkerResultIn 的 JSON 字符串"),
    screenshot: Optional[UploadFile] = File(
        None, description="可选的证据截图（PNG）。截图关闭时不带这个 part"
    ),
    db: Session = Depends(get_db),
    _: Principal = Depends(require_write),
) -> WorkerResultOut:
    """回传一次成功的抓取 —— 落样本 + 引用 + 截图 + 收尾 + 跑 L1 标注。

    **是 multipart 不是 JSON**：截图要跟结果一起回来。迁到大陆节点之后截图一直
    关着（`SCREENSHOT_DIR=` 置空）—— 写在节点本地的图 VPS 读不到，留着只会让
    证据页 404。随结果传回来，这笔债才还上。

    正文放在 ``payload`` 这个表单字段里（``WorkerResultIn`` 的 JSON），
    **截图是可选 part** —— 不带它照样落样本，证据页那个按钮条件渲染，降级是干净的。

    **重复回传是安全的**：已经有样本就回同一个 ``response_id``，既不建第二条样本，
    也不再写一份截图文件。
    """
    try:
        body = WorkerResultIn.model_validate_json(payload)
    except ValidationError as exc:
        # 不让 pydantic 的异常冒成 500 —— 节点看到 500 会当成服务端故障去重试，
        # 而这其实是它自己发错了，重试多少次都一样
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()
        ) from exc

    data = _read_screenshot(screenshot) if screenshot is not None else None
    return WorkerResultOut(**worker_intake.record_result(db, job_id, body, screenshot=data))


@router.post("/jobs/{job_id}/fail", response_model=CrawlJobOut)
def report_failure(
    job_id: int,
    body: WorkerFailIn,
    db: Session = Depends(get_db),
    _: Principal = Depends(require_write),
) -> CrawlJobOut:
    """回传一次失败。

    回的是完整的 ``CrawlJobOut``，节点据此就能知道**这条会不会被自动重排**
    （``status='pending'`` 且 ``next_attempt_at`` 在未来 = 正在退避）。
    """
    job = worker_intake.record_failure(db, job_id, body.reason, kind=body.kind)
    return CrawlJobOut(**job_svc.job_to_out(db, job))


@router.post("/environment", response_model=WorkerEnvironmentOut)
def report_environment(
    body: WorkerEnvironmentIn,
    db: Session = Depends(get_db),
    _: Principal = Depends(require_write),
) -> WorkerEnvironmentOut:
    """自报采集环境，换一个 ``environment_id``（P2-36）。

    节点每 `CRAWL_CREDENTIAL_CHECK_SEC` 报一次，把拿到的 id 带在后续的
    lease 上。**同一种环境只会有一行** —— 那正是
    ``SELECT DISTINCT environment_id ... > 1 就是混了两个出口`` 这条判据成立的前提。
    """
    return WorkerEnvironmentOut(
        environment_id=worker_intake.record_environment(db, body.model_dump())
    )


@router.post("/credentials", response_model=WorkerCredentialsOut)
def report_credentials(
    body: WorkerCredentialsIn,
    db: Session = Depends(get_db),
    _: Principal = Depends(require_write),
) -> WorkerCredentialsOut:
    """自报各平台登录态健康度（P2-07）。

    判级在节点上算（要读 `storage_state` 文件，api 读不到），这里只落库。
    ⚠️ 请求体里**没有任何字段能放 cookie 的值**，这条红线在 schema 上就闭死了。
    """
    return WorkerCredentialsOut(accepted=worker_intake.record_credentials(db, body.items))
