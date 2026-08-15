"""采集环境落库与 run 出口（P2-36）—— 需要真实 Postgres。

指纹规则本身在 `test_crawl_env.py` 里测（纯函数，本机可跑）。
这里钉的是这一条**这个功能存在的全部理由**：

    「这次 run 有没有混着两个出口采」——从「事后查不出来」变成一次查询。

在 VPS 的 api 容器里跑：

    GEO_TEST_DATABASE_URL="$DATABASE_URL" python -m pytest tests/test_run_environments.py -q
"""
from __future__ import annotations

import os

import pytest

TEST_DB = os.environ.get("GEO_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DB, reason="需要 GEO_TEST_DATABASE_URL 指向真实 Postgres"
)

PROBE = "__pytest_env__"

CN = {
    "node_label": "changsha-home", "exit_ip": "120.228.64.174",
    "timezone_id": "Asia/Shanghai", "crawl_mode": "real",
    "credential_region": "cn", "waf_kind": "huawei",
}
SG = {
    "node_label": "vps-sg", "exit_ip": "96.9.213.230",
    "timezone_id": "Asia/Singapore", "crawl_mode": "real",
    "credential_region": "overseas", "waf_kind": "aws",
}


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
    session.execute(text("DELETE FROM runs WHERE note = :p"), {"p": PROBE})
    session.execute(text("DELETE FROM tasks WHERE name = :p"), {"p": PROBE})
    session.execute(text("DELETE FROM prompts WHERE text = :p"), {"p": PROBE})
    session.execute(text("DELETE FROM brands WHERE name = :p"), {"p": PROBE})
    session.execute(
        text("DELETE FROM crawl_environments WHERE node_label IN ('changsha-home','vps-sg')")
    )
    session.commit()


@pytest.fixture
def fixtures(db):
    from app.models import Brand, Prompt, Run, Task

    brand = Brand(name=PROBE)
    db.add(brand)
    db.flush()
    prompt = Prompt(brand_id=brand.id, text=PROBE)
    task = Task(brand_id=brand.id, name=PROBE)
    db.add_all([prompt, task])
    db.flush()
    run = Run(task_id=task.id, note=PROBE)
    db.add(run)
    db.commit()
    return {"prompt": prompt, "run": run, "task": task}


def _job(db, fixtures, env_id=None, status="success"):
    from app.models import CrawlJob

    j = CrawlJob(
        prompt_id=fixtures["prompt"].id, run_id=fixtures["run"].id,
        platform="deepseek", status=status, environment_id=env_id,
    )
    db.add(j)
    db.commit()
    return j


def test_upsert_dedupes_by_fingerprint(db):
    """一行 = 一种环境，不是一行一次抓取。环境很少变，job 每天几十条。"""
    from sqlalchemy import text
    from app.services.crawl_env import compute_fingerprint, upsert_environment

    fields = dict(CN, fingerprint=compute_fingerprint(CN))
    a = upsert_environment(db, fields)
    b = upsert_environment(db, dict(fields))

    assert a == b
    n = db.execute(
        text("SELECT count(*) FROM crawl_environments WHERE node_label='changsha-home'")
    ).scalar()
    assert n == 1


def test_changed_environment_gets_a_new_row(db):
    """出口/时区/登录态任何一维变了都是另一种环境 —— 旧行保留，它是历史。"""
    from app.services.crawl_env import compute_fingerprint, upsert_environment

    a = upsert_environment(db, dict(CN, fingerprint=compute_fingerprint(CN)))
    b = upsert_environment(db, dict(SG, fingerprint=compute_fingerprint(SG)))
    assert a != b


def test_claim_stamps_the_environment(db, fixtures):
    """领取那一刻才是「这台机器接下了这条 job」成为事实的时刻。"""
    from app.services.crawl_env import compute_fingerprint, upsert_environment
    from app.services.crawl_jobs import claim_pending_jobs

    env_id = upsert_environment(db, dict(CN, fingerprint=compute_fingerprint(CN)))
    job = _job(db, fixtures, status="pending")

    claim_pending_jobs(db, limit=50, environment_id=env_id)
    db.refresh(job)
    assert job.environment_id == env_id


def test_claim_without_environment_leaves_it_null(db, fixtures):
    """冷备旧代码、或探测失败时不打标记。**「没记」比编一个准确。**"""
    from app.services.crawl_jobs import claim_pending_jobs

    job = _job(db, fixtures, status="pending")
    claim_pending_jobs(db, limit=50, environment_id=None)
    db.refresh(job)
    assert job.environment_id is None


# ------------------------------------------------------- run 出口：混没混


def test_single_environment_run(db, fixtures):
    from app.api.tasks import _run_environments
    from app.services.crawl_env import compute_fingerprint, upsert_environment

    env_id = upsert_environment(db, dict(CN, fingerprint=compute_fingerprint(CN)))
    for _ in range(3):
        _job(db, fixtures, env_id=env_id)

    envs, unstamped = _run_environments(db, fixtures["run"].id)
    assert len(envs) == 1 and envs[0].n_jobs == 3 and unstamped == 0
    assert envs[0].exit_ip == "120.228.64.174"


def test_mixed_run_is_visible(db, fixtures):
    """**这条就是这个功能存在的全部理由。**

    冷备「只接替不并行」是一条纪律，而纪律需要证据 —— 2026-08-14 那次部署
    把冷备静默拉起来，两台同时在采，事后完全查不出来。现在长度 > 1 就是混了。
    """
    from app.api.tasks import _run_environments
    from app.services.crawl_env import compute_fingerprint, upsert_environment

    cn = upsert_environment(db, dict(CN, fingerprint=compute_fingerprint(CN)))
    sg = upsert_environment(db, dict(SG, fingerprint=compute_fingerprint(SG)))
    for _ in range(4):
        _job(db, fixtures, env_id=cn)
    _job(db, fixtures, env_id=sg)

    envs, _ = _run_environments(db, fixtures["run"].id)

    assert len(envs) == 2, "混了两个出口必须看得出来"
    assert envs[0].n_jobs == 4 and envs[1].n_jobs == 1, "按样本数降序，主环境在前"
    assert {e.exit_ip for e in envs} == {"120.228.64.174", "96.9.213.230"}


def test_old_runs_report_unstamped_not_a_fake_environment(db, fixtures):
    """本功能上线前的 run 会全部 unstamped。**那是事实，不是缺陷** ——
    给它们编一个「默认环境」等于伪造历史。"""
    from app.api.tasks import _run_environments

    for _ in range(3):
        _job(db, fixtures, env_id=None)

    envs, unstamped = _run_environments(db, fixtures["run"].id)
    assert envs == [] and unstamped == 3
