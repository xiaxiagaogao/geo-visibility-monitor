"""`GET /v1/citations/domains` —— 引用域名聚合（P2-37 之后的新需求）。

## 这份数据回答的问题

**「哪些站正在被 AI 引用」** —— 对做 GEO 运营的人来说，这比「AI 说了什么」
更可执行：知道哪些站被引，才知道内容该往哪儿投。

## 口径（2026-08-22 用户拍板）

**按引用次数累加**，一个域名在一条回答里被引 3 次就计 3。

> ⚠️ 这个口径的已知偏向：聚合型站点会把榜单刷高。实测 job 638 的 7 条引用里
> `bitauto.com` 独占 5 条。所以除了 `n_citations`，**另给一个 `n_samples`
> （出现在几条不同样本里）作为诊断** —— 它不参与排序，只是让
> 「23 次里 20 次来自同一条样本」这种情况暴露出来，而不是藏在一个大数字后面。

需要真实 Postgres。
"""
from __future__ import annotations

import os

import pytest

TEST_DB = os.environ.get("GEO_TEST_DATABASE_URL")
PROBE = "__pytest_citedomain__"

behaviour = pytest.mark.skipif(
    not TEST_DB, reason="需要 GEO_TEST_DATABASE_URL 指向真实 Postgres"
)


def _purge(session) -> None:
    from sqlalchemy import text

    p = f"{PROBE}%"
    for sql in (
        "DELETE FROM citations WHERE response_id IN (SELECT r.id FROM raw_responses r JOIN crawl_jobs j ON j.id=r.job_id JOIN prompts pr ON pr.id=j.prompt_id WHERE pr.text LIKE :p)",
        "DELETE FROM mentions WHERE response_id IN (SELECT r.id FROM raw_responses r JOIN crawl_jobs j ON j.id=r.job_id JOIN prompts pr ON pr.id=j.prompt_id WHERE pr.text LIKE :p)",
        "DELETE FROM raw_responses WHERE job_id IN (SELECT id FROM crawl_jobs WHERE prompt_id IN (SELECT id FROM prompts WHERE text LIKE :p))",
        "DELETE FROM crawl_jobs WHERE prompt_id IN (SELECT id FROM prompts WHERE text LIKE :p)",
        "DELETE FROM prompts WHERE text LIKE :p",
        "DELETE FROM brands WHERE name LIKE :p",
    ):
        session.execute(text(sql), {"p": p})
    session.commit()


@pytest.fixture
def db():
    from app.core.db import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        _purge(s)
        s.close()


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.api.deps import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app, base_url="https://testserver")
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def cited(db):
    """两条样本：
    #1 引 aggregator 3 次 + small 1 次    #2 引 aggregator 1 次 + other 1 次

    于是 aggregator 共 4 次 / 2 条样本，small 1 次 / 1 条，other 1 次 / 1 条。
    **aggregator 的 4 次里有 3 次来自同一条样本** —— 这正是要能看出来的那种偏向。
    """
    from app.models import Brand, Citation, CrawlJob, Prompt, RawResponse

    brand = Brand(name=f"{PROBE}_品牌", workspace_id=1)
    db.add(brand)
    db.flush()
    prompt = Prompt(brand_id=brand.id, text=f"{PROBE} 提问", is_active=True)
    db.add(prompt)
    db.flush()

    plan = [
        [("aggregator.example", 3), ("small.example", 1)],
        [("aggregator.example", 1), ("other.example", 1)],
    ]
    for domains in plan:
        job = CrawlJob(prompt_id=prompt.id, platform="tongyi", status="success", sample_index=1)
        db.add(job)
        db.flush()
        resp = RawResponse(
            job_id=job.id, platform="tongyi", prompt_text=prompt.text,
            full_text="够长的正文，避免被判 too_short。" * 4,
            answer_status="ok", search_used=True,
        )
        db.add(resp)
        db.flush()
        i = 0
        for domain, times in domains:
            for _ in range(times):
                i += 1
                db.add(Citation(response_id=resp.id, cite_index=i,
                                url=f"https://{domain}/a{i}", domain=domain,
                                title=f"{domain} 的第 {i} 篇"))
    db.commit()
    return brand.id


def _items(client, brand_id, **params):
    r = client.get("/v1/citations/domains", params={"brand_id": brand_id, **params})
    assert r.status_code == 200, r.text
    return r.json()


@behaviour
def test_counts_every_citation_not_just_distinct_samples(client, db, cited):
    """**口径是按引用次数累加**（用户 2026-08-22 拍板）。

    aggregator 在样本 #1 里被引 3 次、样本 #2 里 1 次 —— 记 4，不是 2。
    """
    by = {i["domain"]: i for i in _items(client, cited)["items"]}
    assert by["aggregator.example"]["n_citations"] == 4


@behaviour
def test_n_samples_exposes_the_concentration(client, db, cited):
    """**诊断字段。** 4 次分布在 2 条样本里 —— 没有这个数，
    「4 次」和「4 条不同样本各引 1 次」在榜单上长得一模一样，
    而它们对「这个站有多大影响力」的含义完全不同。"""
    by = {i["domain"]: i for i in _items(client, cited)["items"]}
    assert by["aggregator.example"]["n_samples"] == 2
    assert by["small.example"]["n_samples"] == 1


@behaviour
def test_sorted_by_citation_count_desc(client, db, cited):
    items = _items(client, cited)["items"]
    counts = [i["n_citations"] for i in items]
    assert counts == sorted(counts, reverse=True)
    assert items[0]["domain"] == "aggregator.example"


@behaviour
def test_totals_describe_the_whole_set_not_just_the_page(client, db, cited):
    """**头部的总数说的是全集，不是当前这一页。**

    第一版把 `n_citations` 写成「返回行的和」，于是 `limit=3` 时它变成了
    前三行的和 —— 而界面上那个数字看起来就是「一共多少条引用」。
    在生产上一查就露馅：run 300 单独有 85 条引用，而带 limit 的全历史查询回 33。

    拿它当百分比的分母会算出一个偏大的占比，而且**永远不会报错**。
    第一版的用例（`n_citations == sum(items)`）恰好把这个 bug 钉成了正确行为 ——
    **一条只验「内部自洽」而不验「和现实一致」的断言，是会保护 bug 的。**
    """
    body = _items(client, cited)
    assert body["n_citations"] == 6      # 全部引用次数
    assert body["n_domains"] == 3        # 全部域名数

    # 截断之后：行少了，但两个总数不变 —— 它们描述的是全集
    top1 = _items(client, cited, limit=1)
    assert len(top1["items"]) == 1
    assert top1["n_citations"] == 6, "总数不该跟着 limit 缩水"
    assert top1["n_domains"] == 3, "域名总数不该跟着 limit 缩水"
    assert sum(i["n_citations"] for i in top1["items"]) < top1["n_citations"]


@behaviour
def test_run_filter_narrows_it(client, db, cited):
    """和 counts 一样要能按 run 收敛 —— 否则看到的是这个品牌历史所有运行混在一起。"""
    body = _items(client, cited, run_id=999999)
    assert body["items"] == [] and body["n_citations"] == 0


@behaviour
def test_a_brand_you_cannot_see_is_404(client, db, cited):
    """归属校验不能漏 —— 这个端点吃 brand_id，漏了就是换个数字看别家。"""
    import inspect

    from app.api import citations as citations_api

    assert "assert_brand_visible" in inspect.getsource(citations_api.citation_domains)


@behaviour
def test_no_citations_is_an_empty_list_not_an_error(client, db):
    """P2-37 之前的样本一条引用都没有 —— 那是正常状态。"""
    from app.models import Brand

    b = Brand(name=f"{PROBE}_空品牌", workspace_id=1)
    db.add(b)
    db.commit()
    body = _items(client, b.id)
    assert body["items"] == [] and body["n_citations"] == 0
