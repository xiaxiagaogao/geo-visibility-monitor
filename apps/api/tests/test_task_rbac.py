"""任务 / 运行的归属校验 —— 不需要数据库，只验代码结构。

守的是 D2 那条最容易漏的：新加的路由必须挂上归属校验，
否则客户能通过 task_id 枚举到别家在监测什么。
"""
from __future__ import annotations

import inspect

from app.api import deps


def test_assert_task_visible_exists():
    assert hasattr(deps, "assert_task_visible")


def test_assert_run_visible_exists():
    assert hasattr(deps, "assert_run_visible")


def test_task_visibility_goes_through_brand():
    """可见性必须走 task → brand → workspace，不能自己造一套判断。"""
    src = inspect.getsource(deps.assert_task_visible)
    assert "assert_brand_visible" in src, "复用既有的品牌可见性，别重造"


def test_run_visibility_goes_through_task():
    src = inspect.getsource(deps.assert_run_visible)
    assert "assert_task_visible" in src


def test_invisible_is_404_not_403():
    """403 等于确认「这个 id 存在但不属于你」，客户据此能枚举出别家有多少任务。"""
    src = inspect.getsource(deps.assert_task_visible)
    assert "_not_found" in src
    assert "403" not in src and "FORBIDDEN" not in src
