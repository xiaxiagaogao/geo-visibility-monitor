from __future__ import annotations

from typing import Dict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

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


def create_run(db: Session, task: Task) -> Run:
    """发起一次运行。

    **顺序不能反：先冻结口径，再建 job。** 反过来的话，两步之间任何一次
    配置修改都会让 job 用新口径跑、快照记旧口径 —— 而这种错不会报错，
    只会让某次 run 的数字对不上它自己的快照。
    """
    run = Run(task_id=task.id, platforms=list(task.platforms or []))
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
