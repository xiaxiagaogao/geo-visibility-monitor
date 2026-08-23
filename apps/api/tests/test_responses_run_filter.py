"""`/v1/responses` 必须能按 run 过滤 —— 任务详情的样本列表列的是「这一次运行」
的样本，不是这个品牌历史所有运行的。不需要数据库。

除了「参数收下了没有」，这里还盯两件更容易出事的：
  1. run_id 必须先过 assert_run_visible —— 否则它是个换个数字就能看别家的洞
  2. 多个条件同时给时 crawl_jobs 只 join 一次 —— 重复 join 不报错，只是悄悄跑歪
"""
from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.api import responses as responses_api
from app.core.security import Principal
from app.models import RawResponse

CLIENT = Principal(kind="user", role="client", workspace_id=1)


# ---------- 参数与授权 ----------


def test_endpoint_accepts_run_id():
    sig = inspect.signature(responses_api.list_responses)
    assert "run_id" in sig.parameters


def test_run_id_is_authorized_before_use():
    """收下参数不算数，先得校验它属不属于这个身份。"""
    src = inspect.getsource(responses_api._resolve_scope)
    assert "assert_run_visible" in src, "run_id 必须过 assert_run_visible"


def test_run_id_counts_as_a_narrowing_condition(fake_db):
    """带了 run_id 就不该再退回「收敛到全部可见品牌」——
    run 已经把范围钉死在一个任务上了，再叠一层只会多两个 join。"""
    scope = responses_api._resolve_scope(
        fake_db(brand_workspace=1),
        CLIENT,
        prompt_id=None,
        brand_id=None,
        run_id=128,
    )
    assert scope is None


def test_client_cannot_borrow_another_workspaces_run(fake_db):
    """**这条是这个参数真正的风险。** run_id 看起来无害，
    不校验的话客户改一个数字就能列出别家的样本。"""
    db = fake_db(brand_workspace=2)  # run→task→brand 落在别家
    with pytest.raises(HTTPException) as e:
        responses_api._resolve_scope(
            db, CLIENT, prompt_id=None, brand_id=None, run_id=128
        )
    assert e.value.status_code == 404, "不可见一律 404，403 会泄露「这个 id 存在」"


def test_no_condition_still_converges_client_to_own_brands(fake_db):
    """一个收敛条件都不给时，原来的兜底不能被这次改动弄丢。"""
    db = fake_db(brand_ids=[34, 35])
    assert responses_api._resolve_scope(
        db, CLIENT, prompt_id=None, brand_id=None, run_id=None
    ) == [34, 35]


# ---------- SQL ----------


def _sql(**overrides) -> str:
    kw = dict(
        platform=None,
        answer_status=None,
        prompt_id=None,
        brand_id=None,
        run_id=None,
        # P2-37 起 _scoped 多了这个条件。默认 None = 不筛，
        # 这些用例盯的是 run_id 的 join 行为，不关心联网标注
        search_used=None,
        allowed_brands=None,
    )
    kw.update(overrides)
    return str(responses_api._scoped(select(RawResponse), **kw))


def test_run_filter_goes_into_sql():
    sql = _sql(run_id=128)
    assert "crawl_jobs.run_id" in sql, "过滤要走 crawl_jobs.run_id"
    assert "JOIN crawl_jobs" in sql


def test_crawl_jobs_is_joined_only_once():
    """prompt_id / run_id / 客户收敛三个条件都走 crawl_jobs。

    重复 join 不会报错，SQLAlchemy 会给第二次一个别名，然后过滤条件落在
    哪个实例上全看运气 —— 拿到的行既可能多也可能少，而页面照常渲染。
    """
    sql = _sql(run_id=128, prompt_id=23, brand_id=34, allowed_brands=[34])
    assert sql.count("JOIN crawl_jobs") == 1
    assert sql.count("JOIN prompts") == 1


def test_count_query_takes_the_same_filters():
    """total 与 items 用同一套条件，否则翻页器会显示一个对不上的总数。"""
    kw = dict(
        platform=None,
        answer_status=None,
        prompt_id=None,
        brand_id=None,
        run_id=128,
        search_used=None,
        allowed_brands=None,
    )
    sql = str(
        responses_api._scoped(select(func.count()).select_from(RawResponse), **kw)
    )
    assert "crawl_jobs.run_id" in sql
    assert "count(" in sql

    # P2-37：新加的条件同样两边都要进，否则筛过之后 total 还是全量 ——
    # 翻页器会给出一个永远翻不到的页数
    counted = str(
        responses_api._scoped(
            select(func.count()).select_from(RawResponse), **{**kw, "search_used": "unknown"}
        )
    )
    assert "search_used IS NULL" in counted
