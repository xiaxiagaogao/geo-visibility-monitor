"""失败分类落库（P2-08）—— 需要真实 Postgres。

分类规则本身在 `test_failure_kinds.py` 里测（纯函数，本机可跑）。
这里只钉「分类真的写进了 crawl_jobs.failure_kind」这一段。

在 VPS 的 api 容器里跑：

    GEO_TEST_DATABASE_URL="$DATABASE_URL" python -m pytest tests/test_fail_job.py -q
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

TEST_DB = os.environ.get("GEO_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DB, reason="需要 GEO_TEST_DATABASE_URL 指向真实 Postgres"
)

PROBE = "__pytest_failkind__"


@pytest.fixture
def db():
    from app.core.db import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        _purge(session)
        session.close()


def _purge(session) -> None:
    from sqlalchemy import text

    session.execute(
        text("DELETE FROM crawl_jobs WHERE prompt_id IN (SELECT id FROM prompts WHERE text = :p)"),
        {"p": PROBE},
    )
    session.execute(text("DELETE FROM prompts WHERE text = :p"), {"p": PROBE})
    session.execute(text("DELETE FROM brands WHERE name = :p"), {"p": PROBE})
    session.commit()


@pytest.fixture
def job(db):
    from app.models import Brand, CrawlJob, Prompt

    brand = Brand(name=PROBE)
    db.add(brand)
    db.flush()
    prompt = Prompt(brand_id=brand.id, text=PROBE)
    db.add(prompt)
    db.flush()
    j = CrawlJob(prompt_id=prompt.id, platform="deepseek", status="running")
    db.add(j)
    db.commit()
    return j


def test_fail_job_records_kind(db, job):
    from app.services.crawl_jobs import fail_job
    from app.services.failure_kinds import TIMEOUT

    fail_job(db, job, RuntimeError("crawl timed out after 165s"))
    db.refresh(job)

    assert job.status == "failed"
    assert job.failure_kind == TIMEOUT
    assert job.finished_at is not None
    assert "timed out" in job.error_message


def test_fail_job_truncates_error_message(db, job):
    """`error_message` 是 TEXT 没有长度限制，但 500 字符之外没有信息量，
    而 Playwright 的报错能带上整页 DOM。"""
    from app.services.crawl_jobs import fail_job

    fail_job(db, job, RuntimeError("x" * 5000))
    db.refresh(job)
    assert len(job.error_message) == 500


def test_explicit_kind_wins_over_classification(db, job):
    """调用方比消息文本更清楚发生了什么时，不该再去猜。"""
    from app.services.crawl_jobs import fail_job
    from app.services.failure_kinds import WORKER_DIED

    # 这句话里带着 "timeout"，光看文本会归成可重试的 timeout
    fail_job(db, job, "timeout while reclaiming", kind=WORKER_DIED)
    db.refresh(job)
    assert job.failure_kind == WORKER_DIED


def test_reclaimed_job_is_marked_worker_died(db, job):
    """僵死回收写的是 worker_died —— 它不在 RETRYABLE_KINDS 里，
    所以「容器被 OOM / 家宽断电」不会被自动重试悄悄掩盖。"""
    from app.services.crawl_jobs import reclaim_stuck_jobs
    from app.services.failure_kinds import WORKER_DIED, is_retryable

    job.started_at = datetime.now(timezone.utc) - timedelta(seconds=1200)
    db.commit()

    assert job.id in reclaim_stuck_jobs(db, older_than_sec=600)
    db.refresh(job)
    assert job.failure_kind == WORKER_DIED
    assert not is_retryable(job.failure_kind)


def test_unknown_failure_is_still_recorded(db, job):
    """认不出来也要写一个值 —— `failure_kind IS NULL` 该只表示「还没失败过」，
    不该和「失败了但没认出来」混在一起。"""
    from app.services.crawl_jobs import fail_job
    from app.services.failure_kinds import UNKNOWN

    fail_job(db, job, RuntimeError("something nobody has seen before"))
    db.refresh(job)
    assert job.failure_kind == UNKNOWN
