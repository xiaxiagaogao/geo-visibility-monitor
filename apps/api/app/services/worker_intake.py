"""采集节点回传结果的落库（P2-34）。

## 为什么单开一个模块

它要调 ``crawl_runner.persist_result``（复用隧道模式那条落库路径），而
``crawl_runner`` 自己 import 了 ``crawl_jobs`` —— 把这些函数塞进 ``crawl_jobs``
会绕成循环 import。放这里，依赖方向是单向的：

    api/worker.py → services/worker_intake.py → services/crawl_runner.py
                                              → services/crawl_jobs.py

## 两条幂等规则，都是被 HTTP 逼出来的

隧道模式下「抓完」和「落库」在同一个进程里，中间不会掉。换成 HTTP 之后，
**节点在大陆家宽、api 在新加坡**，「库里写成功了但 200 没回到节点」是必然会发生
的形态，而节点重试是对的做法。所以：

1. **一条 job 只落一条样本。** 已经有 ``RawResponse`` 就回同一个 id，不再建。
   不做这条，一次网络抖动就多一条样本，而样本直接进 KPI 分母。
2. **重复回传 fail 不再扣 ``attempt``。** 那是重试预算，多扣一次就少试一次。
   靠「只在 ``running`` 时才收」实现 —— 第二发进来时 job 已经不是 running 了。
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import CrawlJob, Prompt
from app.providers.base import CitationData, CrawlResult
from app.schemas.crawl import WorkerResultIn
from app.services.crawl_jobs import fail_job, first_response_id, get_job_or_404
from app.services.crawl_runner import persist_result

logger = logging.getLogger("geo.worker_intake")


def record_result(db: Session, job_id: int, payload: WorkerResultIn) -> dict:
    """收下一条成功结果。**同一条 job 重复回传只会有一条样本。**"""
    job = get_job_or_404(db, job_id)

    existing = first_response_id(db, job.id)
    if existing is not None:
        # 幂等分支：上一发其实成功了，只是 200 没回到节点。**什么都不做**，
        # 把同一个 id 再回一次即可 —— 让节点的重试是安全的
        logger.info("job %s 已有样本 %s，忽略重复回传", job.id, existing)
        return {"job_id": job.id, "response_id": existing, "status": job.status}

    prompt = db.get(Prompt, job.prompt_id)
    if prompt is None:
        # 外键是 ON DELETE CASCADE，正常删不出这种状态。防御性分支，
        # 与 crawl_runner.process_job 里那条同名判断保持一致的处理
        fail_job(db, job, "prompt missing")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="job's prompt no longer exists"
        )

    result = CrawlResult(
        platform=job.platform,
        prompt=prompt.text,  # 服务端的事实，不听节点的
        full_text=payload.full_text,
        citations=[
            CitationData(
                url=c.url,
                title=c.title,
                snippet=c.snippet,
                domain=c.domain,
                cite_index=c.cite_index,
            )
            for c in payload.citations
        ],
        raw_json=payload.raw_json,
        latency_ms=payload.latency_ms,
        screenshot_path=None,  # 第 4 步接 multipart 之后才有
    )
    resp = persist_result(db, job, prompt, result)
    logger.info("worker 回传成功 job_id=%s response_id=%s", job.id, resp.id)
    return {"job_id": job.id, "response_id": resp.id, "status": job.status}


def record_failure(
    db: Session, job_id: int, reason: str, kind: Optional[str] = None
) -> CrawlJob:
    """收下一条失败。**只在 job 还是 ``running`` 时才真的收。**

    不是 running 的两种情况都不该再扣一次 ``attempt``：

    - **重复回传**（第一发成功了但响应没回到节点）；
    - **已被僵死回收**（``CRAWL_STUCK_JOB_SEC`` 把它收成 failed 了）——
      那条路径写的 ``error_message`` 说的是「worker 死了」，再盖一层没有新信息。
    """
    job = get_job_or_404(db, job_id)
    if job.status != "running":
        logger.info("job %s 状态是 %s，不是 running —— 忽略重复的失败回传", job.id, job.status)
        return job
    return fail_job(db, job, reason, kind=kind)
