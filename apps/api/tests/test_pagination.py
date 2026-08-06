"""列表分页（不依赖数据库）—— 只验参数确实传到查询里。

在此之前两个列表接口只有 limit（上限 200）、没有 offset，**翻不了页**。
样本过 200 条后前端只能拿到「最近 N 条」，再也够不到更早的数据。
"""
from __future__ import annotations

import inspect

from app.api import crawl_jobs as jobs_api
from app.api import responses as responses_api
from app.services import crawl_jobs as jobs_svc


def test_responses_list_accepts_offset():
    sig = inspect.signature(responses_api.list_responses)
    assert "offset" in sig.parameters, "/v1/responses 必须支持翻页"


def test_jobs_list_accepts_offset():
    sig = inspect.signature(jobs_api.list_crawl_jobs)
    assert "offset" in sig.parameters, "/v1/crawl-jobs 必须支持翻页"


def test_service_applies_offset_to_query():
    """光收下 offset 参数不算数 —— 必须真的进 SQL。

    这条守的是「加了参数却忘了用」这类静默失效：接口看起来支持翻页，
    实际每页都返回同一批数据。
    """
    src = inspect.getsource(jobs_svc.list_jobs)
    assert ".offset(" in src, "offset 必须作用到查询上，不能只出现在函数签名里"


def test_responses_applies_offset_to_query():
    src = inspect.getsource(responses_api.list_responses)
    assert ".offset(" in src


def test_total_is_independent_of_paging():
    """total 必须是过滤后的全量计数，不受 limit/offset 影响，否则前端算不出页数。"""
    src = inspect.getsource(jobs_svc.list_jobs)
    total_line = next(l for l in src.splitlines() if "total =" in l)
    assert "limit" not in total_line and "offset" not in total_line
