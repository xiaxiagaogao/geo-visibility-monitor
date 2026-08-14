"""自动退避重试落库（P2-16）—— 需要真实 Postgres。

曲线与「重试与否」的判断在 `test_retry_policy.py` 里测（纯函数，本机可跑）。
这里只钉它和数据库那一段的接缝：状态怎么改、claim 认不认那个时刻。

在 VPS 的 api 容器里跑：

    GEO_TEST_DATABASE_URL="$DATABASE_URL" python -m pytest tests/test_auto_retry.py -q
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

TEST_DB = os.environ.get("GEO_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DB, reason="需要 GEO_TEST_DATABASE_URL 指向真实 Postgres"
)

PROBE = "__pytest_retry__"
TIMEOUT_EXC = RuntimeError("Page.goto: Timeout 120000ms exceeded.")


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
def make_job(db):
    """建 job 的工厂 —— 有几条用例要一次建两条来验 claim 的取舍。"""
    from app.models import Brand, CrawlJob, Prompt

    brand = Brand(name=PROBE)
    db.add(brand)
    db.flush()
    prompt = Prompt(brand_id=brand.id, text=PROBE)
    db.add(prompt)
    db.flush()

    def _make(**kw):
        job = CrawlJob(prompt_id=prompt.id, platform="deepseek", **kw)
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    return _make


@pytest.fixture
def retry_on(monkeypatch):
    """打开自动重试。用真的 `Settings` 而不是替身 —— 字段名写错会当场报错。"""
    from app.core.config import Settings

    def _apply(**over):
        fields = {
            "crawl_auto_retry_enabled": True,
            "crawl_max_attempts": 3,
            "crawl_retry_base_sec": 30.0,
            "crawl_retry_max_sec": 300.0,
            # 抖动关掉，否则退避时刻不确定，用例没法钉
            "crawl_retry_jitter": 0.0,
        }
        fields.update(over)  # 先合并再构造 —— 直接 **over 会和上面的显式参数撞
        settings = Settings(**fields)
        monkeypatch.setattr("app.services.crawl_jobs.get_settings", lambda: settings)
        return settings

    return _apply


# ------------------------------------------------------------------ 重排


def test_timeout_is_requeued_with_a_future_next_attempt(db, make_job, retry_on):
    """P2-16 的本体：冷启动被限流的那条不该就此丢掉。"""
    from app.services.crawl_jobs import fail_job
    from app.services.failure_kinds import TIMEOUT

    retry_on()
    job = make_job(status="running", started_at=datetime.now(timezone.utc))
    before = datetime.now(timezone.utc)

    fail_job(db, job, TIMEOUT_EXC)
    db.refresh(job)

    assert job.status == "pending"          # 不是 failed —— 它还会再试
    assert job.attempt == 1
    assert job.failure_kind == TIMEOUT
    assert job.next_attempt_at > before     # 退避到未来某个时刻
    assert job.finished_at is None          # 还没结束
    assert job.started_at is None           # 与 retry_job 一致


def test_requeued_job_is_not_left_in_running(db, make_job, retry_on):
    """留在 running 会被僵死回收当成「worker 死了」收成 failed，
    而那条路径写的 error_message 会把真正的失败原因盖掉。"""
    from app.services.crawl_jobs import fail_job, reclaim_stuck_jobs

    retry_on()
    job = make_job(
        status="running", started_at=datetime.now(timezone.utc) - timedelta(seconds=1200)
    )
    fail_job(db, job, TIMEOUT_EXC)

    assert job.id not in reclaim_stuck_jobs(db, older_than_sec=600)
    db.refresh(job)
    assert job.status == "pending"


# ------------------------------------------------------------------ 终态


def test_switch_off_keeps_todays_behaviour(db, make_job, retry_on):
    """开关是回滚手段：关掉就回到「只分类不重试」，不必 git revert。"""
    from app.services.crawl_jobs import fail_job

    retry_on(crawl_auto_retry_enabled=False)
    job = make_job(status="running")

    fail_job(db, job, TIMEOUT_EXC)
    db.refresh(job)

    assert job.status == "failed"
    assert job.next_attempt_at is None
    assert job.finished_at is not None


def test_login_required_is_terminal_even_with_retry_on(db, make_job, retry_on):
    from app.providers.deepseek_web import DeepSeekLoginRequired
    from app.services.crawl_jobs import fail_job
    from app.services.failure_kinds import LOGIN_REQUIRED

    retry_on()
    job = make_job(status="running")

    fail_job(db, job, DeepSeekLoginRequired("DeepSeek appears to require login."))
    db.refresh(job)

    assert job.status == "failed"
    assert job.failure_kind == LOGIN_REQUIRED
    assert job.next_attempt_at is None


def test_exhausted_attempts_stop_forever(db, make_job, retry_on):
    """**「重试耗尽后仍然 failed，不能无限重排」的落点。**"""
    from app.services.crawl_jobs import fail_job

    retry_on()
    job = make_job(status="running", attempt=2)  # 已经试过两次

    fail_job(db, job, TIMEOUT_EXC)
    db.refresh(job)

    assert job.attempt == 3
    assert job.status == "failed"
    assert job.next_attempt_at is None
    assert "attempt 3/3" in job.error_message


def test_first_attempt_failure_gets_no_noisy_prefix(db, make_job, retry_on):
    """一次就失败的 job 加「attempt 1/3」是噪声。"""
    from app.services.crawl_jobs import fail_job

    retry_on(crawl_auto_retry_enabled=False)
    job = make_job(status="running")

    fail_job(db, job, TIMEOUT_EXC)
    db.refresh(job)
    assert not job.error_message.startswith("attempt")


# ------------------------------------------------------------------ claim 闸门


def test_claim_skips_a_job_still_in_backoff(db, make_job):
    from app.services.crawl_jobs import claim_pending_jobs

    job = make_job(
        status="pending",
        next_attempt_at=datetime.now(timezone.utc) + timedelta(seconds=300),
    )
    claimed = claim_pending_jobs(db, limit=50)
    assert job.id not in [j.id for j in claimed]
    db.refresh(job)
    assert job.status == "pending"


def test_claim_picks_up_a_job_whose_backoff_expired(db, make_job):
    from app.services.crawl_jobs import claim_pending_jobs

    job = make_job(
        status="pending",
        next_attempt_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    assert job.id in [j.id for j in claim_pending_jobs(db, limit=50)]


def test_null_next_attempt_at_means_claimable(db, make_job):
    """向后兼容那一条：迁移前的旧行、以及**冷备那台旧代码 crawler 建的行**，
    这个字段都是 NULL。挡住它们就等于把冷备废掉。"""
    from app.services.crawl_jobs import claim_pending_jobs

    job = make_job(status="pending")
    assert job.next_attempt_at is None
    assert job.id in [j.id for j in claim_pending_jobs(db, limit=50)]


def test_claim_clears_failure_state_but_keeps_attempt(db, make_job):
    """`attempt` 是累计的 —— claim 时清掉就等于重试上限形同虚设。"""
    from app.services.crawl_jobs import claim_pending_jobs
    from app.services.failure_kinds import TIMEOUT

    job = make_job(
        status="pending",
        attempt=1,
        failure_kind=TIMEOUT,
        error_message="Page.goto: Timeout 120000ms exceeded.",
        next_attempt_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    claim_pending_jobs(db, limit=50)
    db.refresh(job)

    assert job.status == "running"
    assert job.attempt == 1          # 保留
    assert job.failure_kind is None  # 清掉
    assert job.error_message is None
    assert job.next_attempt_at is None
