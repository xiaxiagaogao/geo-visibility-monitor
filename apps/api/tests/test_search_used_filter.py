"""按联网标注筛样本（P2-37 的列表侧）—— 需要真实 Postgres。

## 为什么必须在服务端筛

样本列表是**服务端分页**的（`limit`/`offset`）。在前端筛只会筛当前这一页 ——
用户点「已联网」看到 3 条，而第 2 页还有 5 条，他不会知道。
**那是「看着对、其实错」，比不做这个功能糟。**

## 这一档真正盯的那个坑

`search_used` 是三态，而 SQL 里 `NULL` 不参与任何比较：

```sql
WHERE search_used = false   -- NULL 的行**不会**被选中（NULL = false 结果是 NULL）
WHERE search_used IS NULL   -- 只有这样才选得到「不知道」
```

所以「筛未联网」和「筛不知道」必须是两个不同的条件。写错的后果不是报错，
是**把 55 条历史样本悄悄算进「未联网」**（或反过来漏掉），
而界面上看不出任何异常。
"""
from __future__ import annotations

import os

import pytest

TEST_DB = os.environ.get("GEO_TEST_DATABASE_URL")

PROBE = "__pytest_searchfilter__"

behaviour = pytest.mark.skipif(
    not TEST_DB, reason="需要 GEO_TEST_DATABASE_URL 指向真实 Postgres"
)


def _purge(session) -> None:
    from sqlalchemy import text

    p = f"{PROBE}%"
    for sql in (
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
def three_states(db):
    """一条 run 下三条样本：联网 / 确认没联网 / 不知道。"""
    from app.models import Brand, CrawlJob, Prompt, RawResponse

    brand = Brand(name=f"{PROBE}_品牌", workspace_id=1)
    db.add(brand)
    db.flush()
    prompt = Prompt(brand_id=brand.id, text=f"{PROBE} 提问", is_active=True)
    db.add(prompt)
    db.flush()

    made = {}
    for label, value in (("yes", True), ("no", False), ("unknown", None)):
        job = CrawlJob(prompt_id=prompt.id, platform="tongyi", status="success", sample_index=1)
        db.add(job)
        db.flush()
        resp = RawResponse(
            job_id=job.id, platform="tongyi", prompt_text=prompt.text,
            full_text=f"{label} 的正文，够长以免被判 too_short。" * 3,
            answer_status="ok", search_used=value,
        )
        db.add(resp)
        db.flush()
        made[label] = resp.id
    db.commit()
    return made


def _ids(client, **params):
    r = client.get("/v1/responses/summary", params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    # total 必须和过滤后的条数一致 —— 计数查询和取数查询用的是同一套条件，
    # 分叉的话翻页器会显示一个永远翻不到的页数
    assert body["total"] == len(body["items"]), "total 与 items 对不上"
    return {i["id"] for i in body["items"]}


@behaviour
def test_filter_true_returns_only_searched(client, db, three_states):
    got = _ids(client, search_used="true", limit=200)
    assert three_states["yes"] in got
    assert three_states["no"] not in got
    assert three_states["unknown"] not in got


@behaviour
def test_filter_false_excludes_unknown(client, db, three_states):
    """**这条是本文件的核心。**

    SQL 里 `NULL` 不参与比较，写 `= false` 时 NULL 行不会被选中 ——
    这正是我们要的。但如果有人「顺手」写成
    `coalesce(search_used, false) = false`，55 条历史样本会一声不响地
    被算进「未联网」，而界面上完全看不出来。
    """
    got = _ids(client, search_used="false", limit=200)
    assert three_states["no"] in got
    assert three_states["unknown"] not in got, "「不知道」被算成了「未联网」"
    assert three_states["yes"] not in got


@behaviour
def test_filter_unknown_returns_only_nulls(client, db, three_states):
    got = _ids(client, search_used="unknown", limit=200)
    assert three_states["unknown"] in got
    assert three_states["yes"] not in got
    assert three_states["no"] not in got


@behaviour
def test_no_filter_returns_all_three(client, db, three_states):
    got = _ids(client, limit=200)
    assert set(three_states.values()) <= got


@behaviour
def test_the_three_buckets_partition_the_whole_set(client, db, three_states):
    """三桶必须**不重不漏**地覆盖全集 —— 否则报告里的百分比加不到 100%。"""
    everything = _ids(client, limit=200)
    buckets = [_ids(client, search_used=v, limit=200) for v in ("true", "false", "unknown")]

    union = buckets[0] | buckets[1] | buckets[2]
    assert union == everything, "三桶合起来不等于全集"
    assert len(buckets[0]) + len(buckets[1]) + len(buckets[2]) == len(everything), "桶之间有重叠"


@behaviour
def test_a_bogus_value_is_rejected_not_silently_ignored(client, db, three_states):
    """乱传一个值时**不能当成没筛** —— 那会让用户以为自己看到的是筛过的结果。"""
    assert client.get("/v1/responses/summary", params={"search_used": "yes"}).status_code == 422


@behaviour
def test_the_full_list_endpoint_takes_the_same_filter(client, db, three_states):
    """两个端点的过滤参数必须一致（`/summary` 的 docstring 明写了这条）。"""
    r = client.get("/v1/responses", params={"search_used": "unknown", "limit": 200})
    assert r.status_code == 200
    assert {i["id"] for i in r.json()["items"]} >= {three_states["unknown"]}
