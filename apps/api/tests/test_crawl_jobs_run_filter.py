"""`/v1/crawl-jobs` 必须能按 run 过滤，且 run_id 要算「客户也能用的收敛条件」。

这个端点比 /v1/responses 多一层麻烦：客户不带收敛条件时是 400
（任务本身也泄露别家在监测什么）。run_id 加进来之后，那道 400 的判断条件
必须跟着改 —— 否则客户带着一个完全合法的 run_id 仍会被 400 挡在门外，
而任务详情页正是只有 run_id 的场景。不需要数据库。
"""
from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException

from app.api import crawl_jobs as jobs_api
from app.core.security import Principal
from app.services import crawl_jobs as jobs_svc

CLIENT = Principal(kind="user", role="client", workspace_id=1)
OPERATOR = Principal(kind="user", role="operator", workspace_id=None)


def _call(db, principal, **overrides):
    """直接调路由函数。

    参数必须逐个显式传：默认值是 FastAPI 的 ``Query`` 对象，
    不传的话拿到的是 Query 实例而不是 None（而且是真值）。
    """
    kw = dict(
        job_status=None, platform=None, prompt_id=None, run_id=None, limit=50, offset=0
    )
    kw.update(overrides)
    return jobs_api.list_crawl_jobs(db=db, principal=principal, **kw)


# ---------- 参数进 SQL ----------


def test_endpoint_accepts_run_id():
    assert "run_id" in inspect.signature(jobs_api.list_crawl_jobs).parameters


def test_service_accepts_and_applies_run_id():
    """收下参数不算数，必须真的进 SQL。"""
    assert "run_id" in inspect.signature(jobs_svc.list_jobs).parameters
    src = inspect.getsource(jobs_svc.list_jobs)
    assert "CrawlJob.run_id == run_id" in src


def test_route_passes_run_id_down_to_the_service():
    """路由收下却不往下传是这类改动最常见的漏法。"""
    src = inspect.getsource(jobs_api.list_crawl_jobs)
    assert "run_id=run_id" in src


# ---------- RBAC ----------


def test_client_with_only_run_id_is_allowed(monkeypatch, fake_db):
    """**这条是这次改动的重点。** 任务详情页的样本列表只有 run_id ——
    如果 400 的条件还只看 prompt_id，客户点进自己的任务就是一个红错误框。"""
    monkeypatch.setattr(jobs_svc, "list_jobs", lambda *a, **k: ([], 0))
    out = _call(fake_db(brand_workspace=1), CLIENT, run_id=128)
    assert out.total == 0


def test_client_cannot_borrow_another_workspaces_run(fake_db):
    """run_id 不校验的话，客户换个数字就能数出别家某次运行有多少采样、失败几条。"""
    with pytest.raises(HTTPException) as e:
        _call(fake_db(brand_workspace=2), CLIENT, run_id=128)
    assert e.value.status_code == 404, "不可见一律 404，403 会泄露「这个 id 存在」"


def test_client_without_any_narrowing_is_still_rejected(fake_db):
    """原来那道闸不能被这次改动放松。"""
    with pytest.raises(HTTPException) as e:
        _call(fake_db(brand_ids=[34]), CLIENT)
    assert e.value.status_code == 400
    assert "run_id" in e.value.detail, "文案要告诉客户现在也可以用 run_id"


def test_operator_without_any_narrowing_still_lists_everything(monkeypatch, fake_db):
    """运营看全部，那道 400 不该误伤他。"""
    monkeypatch.setattr(jobs_svc, "list_jobs", lambda *a, **k: ([], 0))
    assert _call(fake_db(), OPERATOR).total == 0
