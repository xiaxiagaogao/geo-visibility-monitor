"""/v1/counts 的 run_id 归属校验 —— 结构测试，不需要数据库。

Important 1（整体评审）：`run_id` 传进 `compute_counts` 前必须先过
`assert_run_visible`（否则跨 workspace 的 run_id 能被枚举可见性），
`compute_counts` 内部还要再校验这个 run 确实属于传入的 brand_id
（否则 `competitor_ids` 的快照分支会把别的租户 run 里的
`competitor_brand_id` 原样吐出去）。

行为级验证（真的会抛 404、真的挡住跨租户查询）见
`test_run_brand_mismatch.py`（需要真实 Postgres）。
"""
from __future__ import annotations

import inspect

from app.api import counts as counts_api
from app.services import counts as counts_svc


def test_get_counts_calls_assert_run_visible_when_run_id_given():
    src = inspect.getsource(counts_api.get_counts)
    assert "assert_run_visible" in src, (
        "run_id 和 brand_id、prompt_id 一样是客户能任意改的查询参数，"
        "必须单独过一次可见性校验，不能只信 brand_id 那道"
    )
    idx_run_check = src.index("run_id is not None")
    idx_assert = src.index("assert_run_visible")
    idx_compute = src.index("compute_counts")
    assert idx_run_check < idx_assert < idx_compute, (
        "assert_run_visible 必须在 run_id 非空时、且在调用 compute_counts 之前执行"
    )


def test_compute_counts_validates_run_belongs_to_brand():
    src = inspect.getsource(counts_svc.compute_counts)
    assert "_assert_run_belongs_to_brand" in src, (
        "compute_counts 必须校验 run 确实属于传入的 brand_id —— "
        "这个前提是 competitor_ids 的快照分支能安全读 RunCompetitor 的基础"
    )
    idx_check = src.index("_assert_run_belongs_to_brand")
    idx_comp_ids = src.index("competitor_ids(")
    assert idx_check < idx_comp_ids, (
        "brand/run 匹配校验必须先于 competitor_ids 调用，"
        "否则快照分支会在校验前就把别家 run 的竞品 id 读出来"
    )


def test_assert_run_belongs_to_brand_raises_404_style():
    """结构性冒烟：函数体必须用 404，不能用 403（枚举风险，见 deps.py 的 _not_found）。"""
    src = inspect.getsource(counts_svc._assert_run_belongs_to_brand)
    assert "HTTP_404_NOT_FOUND" in src
    assert "HTTP_403_FORBIDDEN" not in src
