"""建/改任务时的平台 code 校验 —— 纯逻辑，不需要数据库。

根因：services/crawl_jobs.py 的 create_jobs 对平台 code 有两道校验
（is_known → is_runnable），注释写明「未接入的平台在这里就挡掉，以前放行到
worker 才 RuntimeError，用户看到的是『抓取失败』而不是『这个平台没接』」。
Task 5 的路由（create_task / update_task）漏掉了这道防线 —— 这条补上。
"""
from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api import tasks as tasks_api
from app.core.config import get_settings
from app.schemas.task import TaskUpdate
from app.services import tasks as task_svc


def test_validate_platforms_referenced_by_create_task():
    src = inspect.getsource(tasks_api.create_task)
    assert "validate_platforms" in src


def test_validate_platforms_referenced_by_update_task():
    src = inspect.getsource(tasks_api.update_task)
    assert "validate_platforms" in src


def test_unknown_platform_code_rejected():
    with pytest.raises(HTTPException) as exc:
        task_svc.validate_platforms(["not-a-real-platform"])
    assert exc.value.status_code == 400


def test_known_and_runnable_platform_passes():
    """fake 模式（默认）下所有已知平台都可跑 —— 不抛即通过。"""
    task_svc.validate_platforms(["deepseek"])


@pytest.fixture
def real_crawl_mode(monkeypatch):
    """doubao/kimi/tongyi 是「已知但没有 real Provider」的平台 ——
    只有切到 real 模式才能触发「不可跑」这一档，fake 模式下全部放行。
    """
    monkeypatch.setenv("CRAWL_MODE", "real")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_known_but_unrunnable_platform_rejected_in_real_mode(real_crawl_mode):
    with pytest.raises(HTTPException) as exc:
        task_svc.validate_platforms(["doubao"])
    assert exc.value.status_code == 400


def test_deepseek_still_runnable_in_real_mode(real_crawl_mode):
    """deepseek 有 real Provider —— real 模式下不该被这道校验误伤。"""
    task_svc.validate_platforms(["deepseek"])


def test_task_update_schema_rejects_empty_platforms():
    """PATCH {"platforms": []} 必须在 schema 层就被拒。

    改之前 TaskUpdate.platforms 缺 min_length=1（TaskCreate 有），空列表能
    通过校验，task_svc.validate_platforms([]) 空循环放行，task.platforms
    被写成 []；此后每次发起运行三层循环的中间层空转，静默变成 0-job 空转 run。
    """
    with pytest.raises(ValidationError):
        TaskUpdate(platforms=[])


def test_task_update_schema_still_allows_omitted_platforms():
    """反向用例：不传 platforms 字段（沿用旧值）不该被这条新校验误伤。"""
    body = TaskUpdate()
    assert body.platforms is None


def test_task_update_schema_allows_nonempty_platforms():
    body = TaskUpdate(platforms=["deepseek"])
    assert body.platforms == ["deepseek"]
