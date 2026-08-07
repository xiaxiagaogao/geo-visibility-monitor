"""把 run_id 为空的历史 job 归到一个补建的 run 下。

现有 35 条安踏样本是在 Task/Run 存在之前跑的，run_id 为 NULL，
在任务式 IA 里会完全不可见 —— 而它是目前唯一的真实数据。

快照按**当前**配置补：这是没办法的事，当时的提问集与竞品集没有记录。
所以补出来的 run 带 note 说明这一点，不要当成和后续 run 同等可比。

默认只读，加 --apply 才写库 —— 和 data_governance_min.py 的默认**相反**：
那个脚本删的是已经判定为垃圾的行（fake 样本、空 job），跑错了最多丢几条
脏数据，且都在同一张表里，后果可控。这个脚本会**建新实体**（Task、Run
及其快照行）、**批量改外键**（把 crawl_jobs.run_id 从 NULL 改写成新 run
的 id），一次改动跨四张表，而且没有「反正本来就是要清的」这层安全网——
--brand-id 传错，就是把别的品牌的历史样本错误地并进一个陌生 run，
且改的是外键，不是简单能从「反正是垃圾」推出可以随便删。所以这里反过来：
不加任何参数 = 只打印会发生什么，不碰库；显式 --apply 才真的写。

（原计划文档里的 --dry-run 已改名去掉：默认即只读，不再需要一个单独的
「只读」开关；保留一个不做任何事的 --dry-run 反而容易让人以为它能盖过
--apply，两个开关一起传时到底谁赢不直观。现在只有一个开关，传了就是写，
不传就是看。）

用法：
    python -m app.scripts.backfill_run --brand-id 34          # 预览，不写库
    python -m app.scripts.backfill_run --brand-id 34 --apply  # 真的执行
"""
from __future__ import annotations

import argparse

from sqlalchemy import func, select

from app.core.db import SessionLocal
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

# 刻意不 import create_run —— 它会再建一批新 job，而回填要的是把旧 job 挂上去

NOTE = "历史回填：Task/Run 引入前的样本。快照按回填时的配置补，与后续运行不完全可比。"


def _gather(db, brand_id: int):
    """算出「会发生什么」，纯查询，不写库。预览分支和 --apply 分支共用，
    保证操作前看到的和实际执行的是同一份信息。"""
    orphan_ids = list(
        db.scalars(
            select(CrawlJob.id)
            .join(Prompt, Prompt.id == CrawlJob.prompt_id)
            .where(Prompt.brand_id == brand_id, CrawlJob.run_id.is_(None))
        )
    )
    platforms = (
        sorted(
            set(db.scalars(select(CrawlJob.platform).where(CrawlJob.id.in_(orphan_ids))))
        )
        if orphan_ids
        else []
    )
    n_prompts = (
        db.scalar(select(func.count()).select_from(Prompt).where(Prompt.brand_id == brand_id))
        or 0
    )
    n_competitors = (
        db.scalar(
            select(func.count())
            .select_from(CompetitorLink)
            .where(CompetitorLink.brand_id == brand_id)
        )
        or 0
    )
    return orphan_ids, platforms, n_prompts, n_competitors


def _print_plan(brand, brand_id, task_name, orphan_ids, platforms, n_prompts, n_competitors) -> None:
    """打印这次执行会造成什么效果 —— 执行前要能靠这份输出判断「这就是我要的」。"""
    print(f"品牌 {brand_id} {brand.name if brand else '(不存在)'}")
    if not orphan_ids:
        print("无主 job：0 条 —— 无事可做，不会创建 task/run。")
        return
    print(f"无主 job：{len(orphan_ids)} 条，涉及平台：{platforms}")
    print(f"会创建 task「{task_name}」，挂在品牌 {brand_id}（{brand.name if brand else '?'}）下")
    print(f"会创建 1 个 run，快照进去 {n_prompts} 条提问、{n_competitors} 个竞品")
    print(f"会把这 {len(orphan_ids)} 条 job 挂上这个 run（平台：{platforms}）")


def _build_arg_parser() -> argparse.ArgumentParser:
    """单独抽出来，好让测试不靠跑 main()（会连数据库）就能验参数定义。"""
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand-id", type=int, required=True)
    ap.add_argument("--task-name", default="历史监测集")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="真正写库。不加则只打印会发生什么，不碰数据库。",
    )
    return ap


def main() -> None:
    args = _build_arg_parser().parse_args()

    db = SessionLocal()
    try:
        brand = db.get(Brand, args.brand_id)
        orphan_ids, platforms, n_prompts, n_competitors = _gather(db, args.brand_id)
        _print_plan(
            brand, args.brand_id, args.task_name, orphan_ids, platforms, n_prompts, n_competitors
        )

        if not args.apply:
            print("以上是预览，未写入。加 --apply 才会真正执行。")
            return

        if not orphan_ids:
            # _print_plan 已经说明「无事可做」，这里不重复打印，直接结束。
            return

        task = Task(
            brand_id=args.brand_id,
            name=args.task_name,
            platforms=platforms,
            samples=1,  # 回填不再建 job，采样数只作展示
        )
        db.add(task)
        db.flush()

        # create_run 会建 job，这里不要 —— 手工建空 run 再挂旧 job
        run = Run(task_id=task.id, platforms=platforms, note=NOTE)
        db.add(run)
        db.flush()
        for p in db.scalars(select(Prompt).where(Prompt.brand_id == args.brand_id)):
            db.add(RunPrompt(run_id=run.id, prompt_id=p.id, prompt_text=p.text))

        for rid, rname in db.execute(
            select(CompetitorLink.competitor_brand_id, Brand.name)
            .join(Brand, Brand.id == CompetitorLink.competitor_brand_id)
            .where(CompetitorLink.brand_id == args.brand_id)
        ):
            db.add(RunCompetitor(run_id=run.id, competitor_brand_id=rid, brand_name=rname))

        db.query(CrawlJob).filter(CrawlJob.id.in_(orphan_ids)).update(
            {"run_id": run.id}, synchronize_session=False
        )
        db.commit()
        print(f"回填完成：task={task.id} run={run.id} 挂上 {len(orphan_ids)} 条 job")
    finally:
        db.close()


if __name__ == "__main__":
    main()
