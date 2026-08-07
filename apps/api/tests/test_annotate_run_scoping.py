"""annotate.py 的竞品口径要贯穿到抽取层 —— 结构测试，不需要数据库。

Important 2（整体评审）：`target_brand_ids` 原来只查活的 `CompetitorLink`，
`annotate_response` 拿到 `job` 却从不碰 `job.run_id`。run 冻结的竞品集
是 [A, B]，如果这批 job 完成前有人整体替换了品牌的竞品配置，或者对失败
job 做了 retry，抽取层会按「当时的活配置」生成 Mention 行，跟之后
`/v1/counts?run_id=` 用 RunCompetitor 快照算出的 track_ids 对不上 ——
B 从「有算」悄悄变成「未算」，不报错、不可见。

行为级验证（真的读了快照、真的没读当前配置）见
`test_annotate_run_snapshot.py`（需要真实 Postgres）。
"""
from __future__ import annotations

import inspect

from app.services import annotate as annotate_svc


def test_target_brand_ids_accepts_run_id():
    sig = inspect.signature(annotate_svc.target_brand_ids)
    assert "run_id" in sig.parameters
    assert sig.parameters["run_id"].default is None, (
        "run_id 必须可选，默认 None —— ad-hoc job（没有 run 归属）行为不能变"
    )


def test_target_brand_ids_reads_run_competitor_when_run_id_given():
    src = inspect.getsource(annotate_svc.target_brand_ids)
    assert "RunCompetitor" in src, (
        "带 run_id 时必须读 RunCompetitor 快照，不能查当前 CompetitorLink"
    )
    assert "CompetitorLink" in src, "不带 run_id 时（ad-hoc job）仍要退回当前配置"


def test_target_brand_ids_keeps_owner_brand_first():
    src = inspect.getsource(annotate_svc.target_brand_ids)
    idx_ids_init = src.index("ids = [owner_brand_id]")
    idx_run_branch = src.index("if run_id is not None")
    assert idx_ids_init < idx_run_branch, (
        "owner_brand_id 必须先放进结果里，快照分支只应该追加竞品，不能把本品挤掉"
    )


def test_annotate_response_passes_job_run_id_to_target_brand_ids():
    """收下 run_id 参数不算数 —— annotate_response 必须真的把 job.run_id 传进去，
    否则这条修复只是加了个没人用的可选参数。
    """
    src = inspect.getsource(annotate_svc.annotate_response)
    assert "target_brand_ids(db, prompt.brand_id, job.run_id)" in src, (
        "annotate_response 必须把 job.run_id 传给 target_brand_ids，"
        "而不是只用 prompt.brand_id 查当前配置"
    )
