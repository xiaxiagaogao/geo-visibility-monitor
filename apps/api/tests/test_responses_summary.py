"""`/v1/responses/summary` —— 列表用的轻量投影。不需要数据库。

这个端点存在的唯一理由是**不传 full_text**。所以这里盯的就是那件事：
schema 里没有那两个大字段、SQL 里也没 select 它们，
以及一个纯路由层的坑：/summary 必须声明在 /{response_id} 之前。
"""
from __future__ import annotations

from sqlalchemy import select

from app.api import responses as responses_api
from app.schemas.crawl import RawResponseSummaryOut

HEAVY = ("full_text", "raw_json")


def test_schema_has_no_heavy_fields():
    """大字段在类型上就该不存在。

    改成「可选」是另一种做法，但那让类型撒谎：前端拿到 undefined 不会报错，
    只会渲染出一片空白 —— 而这正是这个项目在 m_first 上已经踩过的坑。
    """
    fields = RawResponseSummaryOut.model_fields
    for name in HEAVY:
        assert name not in fields, f"轻量投影不该有 {name}"
    # 列表页真正要用的那几个必须在
    for name in ("prompt_text", "text_preview", "text_length", "answer_status", "mentions"):
        assert name in fields


def test_sql_never_selects_the_big_columns():
    """投影得真的落到 SQL 上 —— 否则省的只是 JSON，数据库照样把大列传过来。"""
    sql = str(select(*responses_api._summary_columns()))
    assert "raw_json" not in sql
    assert "substr(raw_responses.full_text" in sql, "正文只以 substr 出现"
    assert "length(raw_responses.full_text" in sql
    # 除 substr / length 这两处派生值外，不该有裸的 full_text 列
    assert sql.count("raw_responses.full_text") == 2


def test_summary_route_is_declared_before_the_id_route():
    """FastAPI 按声明顺序匹配。

    反过来的话 /summary 会先撞上 /{response_id}，被拿去解析成 int，
    得到一个 422 —— 而这种错只在真跑起来时才看得见。
    """
    paths = [r.path for r in responses_api.router.routes]
    assert "/v1/responses/summary" in paths
    assert paths.index("/v1/responses/summary") < paths.index("/v1/responses/{response_id}")


def test_summary_takes_the_same_filters_as_the_list():
    """两个端点的过滤参数必须一致，否则前端换个端点就得换一套查询拼装。"""
    import inspect

    listed = set(inspect.signature(responses_api.list_responses).parameters)
    summary = set(inspect.signature(responses_api.list_response_summaries).parameters)
    assert listed == summary
