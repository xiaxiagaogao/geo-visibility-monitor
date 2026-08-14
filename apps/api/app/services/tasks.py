from __future__ import annotations

from typing import Dict, Iterable, Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Brand,
    CompetitorLink,
    CrawlJob,
    Prompt,
    Run,
    RunCompetitor,
    RunPrompt,
    Task,
)
from app.providers import registry

# job 状态优先级：只要还有没跑完的，run 就没跑完
_UNFINISHED = ("running", "pending")


def derive_run_status(counts: Dict[str, int]) -> str:
    """由 job 状态计数派生 run 状态。

    **不落库。** 存一份就要有人同步，而 job 状态在 worker 里变、
    run 在 API 里变，两者迟早不一致 —— 而一个不一致的状态列
    比没有状态列更糟，因为它看起来权威。

    ``partial`` 是独立一档：部分成功报成 success 会让人以为
    35 条都在，实际分母少了一截，所有比率静默偏高。
    """
    total = sum(counts.values())
    if total == 0:
        return "empty"
    for st in _UNFINISHED:
        if counts.get(st, 0) > 0:
            return st
    ok = counts.get("success", 0)
    if ok == total:
        return "success"
    if ok == 0:
        return "failed"
    return "partial"


def create_run(db: Session, task: Task, note: Optional[str] = None) -> Run:
    """发起一次运行。

    **顺序不能反：先冻结口径，再建 job。** 反过来的话，两步之间任何一次
    配置修改都会让 job 用新口径跑、快照记旧口径 —— 而这种错不会报错，
    只会让某次 run 的数字对不上它自己的快照。
    """
    # note 在这里写死，而不是建完再 UPDATE —— 发起与口径说明是同一件事，
    # 分两步就会出现「run 建好了但 note 还没写」的中间态
    run = Run(task_id=task.id, platforms=list(task.platforms or []), note=note or None)
    db.add(run)
    db.flush()  # 拿 run.id

    prompts = list(
        db.scalars(
            select(Prompt)
            .where(Prompt.brand_id == task.brand_id, Prompt.is_active.is_(True))
            .order_by(Prompt.id)
        )
    )
    for p in prompts:
        db.add(RunPrompt(run_id=run.id, prompt_id=p.id, prompt_text=p.text))

    rivals = list(
        db.execute(
            select(CompetitorLink.competitor_brand_id, Brand.name)
            .join(Brand, Brand.id == CompetitorLink.competitor_brand_id)
            .where(CompetitorLink.brand_id == task.brand_id)
            .order_by(CompetitorLink.competitor_brand_id)
        )
    )
    for rival_id, rival_name in rivals:
        db.add(
            RunCompetitor(
                run_id=run.id, competitor_brand_id=rival_id, brand_name=rival_name
            )
        )

    for p in prompts:
        for platform in run.platforms:
            for i in range(1, (task.samples or 1) + 1):
                db.add(
                    CrawlJob(
                        run_id=run.id,
                        prompt_id=p.id,
                        platform=platform,
                        sample_index=i,
                    )
                )

    db.commit()
    db.refresh(run)
    return run


def run_job_status_counts(db: Session, run_id: int) -> dict:
    """该 run 下 job 的状态计数，喂给 derive_run_status。"""
    rows = db.execute(
        select(CrawlJob.status, func.count())
        .where(CrawlJob.run_id == run_id)
        .group_by(CrawlJob.status)
    )
    return {status: n for status, n in rows}


def validate_platforms(platforms: Iterable[str]) -> None:
    """建任务 / 改 platforms 时，把打错字或未接入的平台挡在这里。

    照 ``services/crawl_jobs.py`` 里 ``create_jobs`` 的两道校验来（``is_known``
    → ``is_runnable``），理由与那边的注释一致：不挡的话 ``create_run`` 会为这些
    code 批量建 job，real 模式下逐个抛 RuntimeError 被兜底标成 ``failed`` ——
    用户看到一堆「抓取失败」，真相是「这个平台没接」，两者排查方向完全不同。

    放在服务层而不是路由/schema 层：``create_jobs`` 就是在服务层做这件事，
    这里保持一致；且校验依赖 ``crawl_mode`` 这个运行期配置，不是纯粹的输入形状
    校验，不适合放进 Pydantic validator。
    """
    crawl_mode = get_settings().crawl_mode
    for code in platforms:
        if not registry.is_known(code):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"platform '{code}' unknown; must be one of {list(registry.known_codes())}",
            )
        if not registry.is_runnable(code, crawl_mode=crawl_mode):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"platform '{code}' 尚未接入（Provider 未实现），无法发起真实抓取。"
                    f" 当前可用：{[c for c in registry.known_codes() if registry.is_runnable(c, crawl_mode=crawl_mode)]}"
                ),
            )
