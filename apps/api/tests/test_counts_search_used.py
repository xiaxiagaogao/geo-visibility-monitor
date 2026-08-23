"""`/v1/counts?group_by=search_used` —— 按联网标注分桶（P2-37 / §4.0.1）。

§4.0.1 的口径原文是「**记录 search 是否激活；无搜索输出是结果，不是废样本**」，
而「记录」要能变成报告，就得能分桶。这是那句口径里最后一块没兑现的。

## 这一档盯的两件事

1. **三桶不重不漏。** 分桶报告的百分比要能加到 100%，
   而 `search_used` 是三态 —— 少一桶或多一桶都不会报错，只会让数字对不上。
2. **`null` 自成一桶，桶名不能叫「没联网」。** 库里有 55 条 P2-37 之前的样本，
   把它们并进「未联网」就是在报告里凭空断言一件没测过的事。

需要真实 Postgres。
"""
from __future__ import annotations

import os

import pytest

TEST_DB = os.environ.get("GEO_TEST_DATABASE_URL")
PROBE = "__pytest_countsbucket__"

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
def brand_with_three_states(db):
    """本品在三种联网状态下各一条有效样本，其中两条提及了本品。"""
    from app.models import Brand, CrawlJob, Mention, Prompt, RawResponse

    brand = Brand(name=f"{PROBE}_品牌", workspace_id=1)
    db.add(brand)
    db.flush()
    prompt = Prompt(brand_id=brand.id, text=f"{PROBE} 提问", is_active=True)
    db.add(prompt)
    db.flush()

    # (search_used, 是否提及本品)
    for value, mentioned in ((True, True), (False, True), (None, False)):
        job = CrawlJob(prompt_id=prompt.id, platform="tongyi", status="success", sample_index=1)
        db.add(job)
        db.flush()
        resp = RawResponse(
            job_id=job.id, platform="tongyi", prompt_text=prompt.text,
            full_text="够长的正文，避免被判成 too_short。" * 4,
            answer_status="ok", search_used=value,
        )
        db.add(resp)
        db.flush()
        db.add(Mention(
            response_id=resp.id, brand_id=brand.id, mentioned=mentioned,
            mention_type="body" if mentioned else "none",
            position_rank=1 if mentioned else None,
        ))
    db.commit()
    return brand.id


def _series(client, brand_id):
    r = client.get("/v1/counts", params={"brand_id": brand_id, "group_by": "search_used"})
    assert r.status_code == 200, r.text
    return {s["key"]: s for s in r.json()["series"]}


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


@behaviour
def test_three_buckets_appear(client, db, brand_with_three_states):
    series = _series(client, brand_with_three_states)
    assert set(series) == {"true", "false", "unknown"}


@behaviour
def test_the_unknown_bucket_is_not_called_no_search(client, db, brand_with_three_states):
    """**桶名不能骗人。** `unknown` 是「我们不知道」，不是「没联网」——
    库里 55 条 P2-37 之前的样本都会落进这一桶。"""
    series = _series(client, brand_with_three_states)
    assert "unknown" in series
    assert "false" in series
    assert series["unknown"]["key"] != series["false"]["key"]


@behaviour
def test_buckets_partition_the_denominator(client, db, brand_with_three_states):
    """**三桶的 n_valid 之和必须等于总的 n_valid** —— 否则报告里的百分比加不到 100%。"""
    r = client.get("/v1/counts", params={"brand_id": brand_with_three_states})
    whole = r.json()["denominator"]["n_valid"]

    series = _series(client, brand_with_three_states)
    assert sum(s["denominator"]["n_valid"] for s in series.values()) == whole


@behaviour
def test_mentions_land_in_the_right_bucket(client, db, brand_with_three_states):
    """联网那条提及了、未记录那条没提及 —— 分桶不能把它们串了。"""
    series = _series(client, brand_with_three_states)
    assert series["true"]["brand"]["m_mentioned"] == 1
    assert series["false"]["brand"]["m_mentioned"] == 1
    assert series["unknown"]["brand"]["m_mentioned"] == 0


@behaviour
def test_a_bogus_group_by_is_still_rejected(client, db, brand_with_three_states):
    r = client.get("/v1/counts", params={"brand_id": brand_with_three_states, "group_by": "banana"})
    assert r.status_code == 400
    assert "search_used" in r.json()["detail"], "报错要列全合法取值，否则还得回去翻代码"
