"""任务路由的形状 —— 不需要数据库。"""
from __future__ import annotations

import inspect

from app.api import tasks as tasks_api


def test_list_tasks_supports_paging():
    sig = inspect.signature(tasks_api.list_tasks)
    assert "limit" in sig.parameters and "offset" in sig.parameters


def test_create_task_requires_write():
    """建任务是写操作，客户不许碰。"""
    src = inspect.getsource(tasks_api.create_task)
    assert "require_write" in src


def test_start_run_requires_write():
    src = inspect.getsource(tasks_api.start_run)
    assert "require_write" in src


def test_get_task_checks_visibility():
    src = inspect.getsource(tasks_api.get_task)
    assert "assert_task_visible" in src


def test_list_tasks_scopes_to_visible():
    """列表必须服务端收敛，不能靠前端自己过滤。"""
    src = inspect.getsource(tasks_api.list_tasks)
    assert "visible_task_ids" in src or "visible_brand_ids" in src


def test_latest_run_endpoint_exists():
    """客户首页分流要用：我这个 workspace 下最新一次运行是哪个。"""
    assert hasattr(tasks_api, "latest_run")


def test_latest_run_scopes_to_visible():
    """只有 hasattr 证明不了它没有对全库开放 —— 必须看它真的按可见性收敛过。"""
    src = inspect.getsource(tasks_api.latest_run)
    assert "visible_task_ids" in src


def test_update_task_requires_write():
    """改任务（含 platforms/samples/is_active）是写操作，客户不许碰。"""
    src = inspect.getsource(tasks_api.update_task)
    assert "require_write" in src


def test_update_task_checks_visibility():
    src = inspect.getsource(tasks_api.update_task)
    assert "assert_task_visible" in src


def test_list_runs_checks_visibility():
    """列某任务下的历次运行，得先证明这个任务对当前身份可见。"""
    src = inspect.getsource(tasks_api.list_runs)
    assert "assert_task_visible" in src


def test_get_run_checks_visibility():
    src = inspect.getsource(tasks_api.get_run)
    assert "assert_run_visible" in src
