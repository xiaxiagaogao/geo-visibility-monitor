"""counts 必须能按 run 过滤 —— 任务详情的 KPI 是「这一次运行」的数,
不是这个品牌历史所有样本的数。不需要数据库。
"""
from __future__ import annotations

import inspect

from app.api import counts as counts_api
from app.services import counts as counts_svc


def test_endpoint_accepts_run_id():
    sig = inspect.signature(counts_api.get_counts)
    assert "run_id" in sig.parameters


def test_service_applies_run_filter():
    """收下参数不算数,必须真的进 SQL。"""
    src = inspect.getsource(counts_svc)
    assert "run_id" in src, "counts 服务层必须用上 run_id"
    assert "CrawlJob.run_id" in src, "过滤要走 crawl_jobs.run_id"


def test_competitors_come_from_snapshot_when_run_given():
    """**这条是这个任务真正的重点。**

    只给响应集合加 run 过滤是不够的 —— 分母(提问集)对上了,
    但竞品集如果还查当前的 CompetitorLink,快照就只用了一半:
    八月给品牌加一个竞品,七月那次 run 的缺口清单和竞品列照样被重算。

    建 job 时用冻结快照、统计时绕开快照查当前配置,是自相矛盾的。
    """
    src = inspect.getsource(counts_svc)
    assert "RunCompetitor" in src, (
        "带 run_id 时竞品集必须取自 RunCompetitor 快照,不能查当前 CompetitorLink"
    )
