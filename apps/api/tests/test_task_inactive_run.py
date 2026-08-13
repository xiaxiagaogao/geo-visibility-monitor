"""停用的任务不许发起运行（不依赖数据库）。

背景：`start_run` 原先不检查 `task.is_active`，于是「已停用」只是任务列表里
的一个徽章。而 `create_run` **是**按 `Prompt.is_active` 过滤提问词的 ——
同一个字段名在两处一处当真、一处装饰，是那种没人会当场发现的不一致。

之前不明显，是因为前端从没有停用任务的入口（`is_active` 只读不写）。
A6 的任务编辑把入口做出来了，这条就必须补上，否则界面上写着「停用」
而它照样跑。
"""
from __future__ import annotations

import inspect

from app.api import tasks as tasks_api


def test_start_run_checks_is_active():
    src = inspect.getsource(tasks_api.start_run)
    assert "is_active" in src, "start_run 必须检查任务是否停用"


def test_inactive_is_400_not_404():
    """400 而不是 404 —— 任务确实存在、你也看得见，只是它被停用了。

    报 404 会让人以为任务没了或者没权限，排查方向完全错。
    """
    src = inspect.getsource(tasks_api.start_run)
    idx = src.index("is_active")
    after = src[idx:]
    assert "HTTP_400_BAD_REQUEST" in after
    # 文案要说清楚下一步做什么，不能只说「不行」
    assert "enable" in after.lower()


def test_create_run_still_filters_inactive_prompts():
    """反向确认另一半没被改坏：提问词的 is_active 过滤仍在。"""
    from app.services import tasks as task_svc

    src = inspect.getsource(task_svc.create_run)
    assert "Prompt.is_active" in src
