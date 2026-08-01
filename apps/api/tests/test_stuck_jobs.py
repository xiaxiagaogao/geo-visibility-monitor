"""僵死 running job 的回收 —— 需要真实 Postgres。

本机不装 Docker（docs/08：本机只写代码），所以默认跳过。
在 VPS 的 api 容器里跑：

    GEO_TEST_DATABASE_URL="$DATABASE_URL" python -m pytest tests/test_stuck_jobs.py -q

注意：会往库里写少量测试数据，跑完自行回滚（本测试用例结束时会删掉自己建的行）。
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

TEST_DB = os.environ.get("GEO_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DB, reason="需要 GEO_TEST_DATABASE_URL 指向真实 Postgres"
)


PROBE = "__pytest_stuck__"


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
    """按外键顺序清干净，不依赖级联行为（那是 test_cascade_delete 的事）。"""
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


def test_old_running_job_is_reclaimed(db, job):
    from app.services.crawl_jobs import reclaim_stuck_jobs

    job.started_at = datetime.now(timezone.utc) - timedelta(seconds=1200)
    db.commit()

    assert job.id in reclaim_stuck_jobs(db, older_than_sec=600)
    db.refresh(job)
    assert job.status == "failed"
    assert "reclaimed" in job.error_message
    assert job.finished_at is not None


def test_fresh_running_job_is_left_alone(db, job):
    """正在跑的任务不能被误杀。"""
    from app.services.crawl_jobs import reclaim_stuck_jobs

    job.started_at = datetime.now(timezone.utc) - timedelta(seconds=30)
    db.commit()

    assert job.id not in reclaim_stuck_jobs(db, older_than_sec=600)
    db.refresh(job)
    assert job.status == "running"


def test_reclaimed_job_can_be_requeued(db, job):
    """原先 retry 只放行 failed/success，running 卡死后 API 层无法自救。"""
    from app.services.crawl_jobs import retry_job

    job.started_at = datetime.now(timezone.utc) - timedelta(seconds=1200)
    db.commit()

    requeued = retry_job(db, job.id)
    assert requeued.status == "pending"
    assert requeued.started_at is None
    assert requeued.error_message is None
