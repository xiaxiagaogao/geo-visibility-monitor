"""Task / Run 建表与外键 —— 需要真实 Postgres。

在 VPS 的 api 容器里跑：

    docker exec -w /app/apps/api -e PYTHONPATH=. \
      -e GEO_TEST_DATABASE_URL="$DATABASE_URL" geo-api python -m pytest tests/ -q
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import func, inspect as sa_inspect, select

TEST_DB = os.environ.get("GEO_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DB, reason="需要 GEO_TEST_DATABASE_URL 指向真实 Postgres"
)

PROBE = "__pytest_task_run_cascade__"


@pytest.fixture
def conn():
    from app.core.db import engine

    with engine.connect() as c:
        yield c


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
    """按外键顺序清掉本测试造的数据（不依赖待测的级联行为）。"""
    from sqlalchemy import text

    session.execute(
        text(
            """
            DELETE FROM crawl_jobs WHERE prompt_id IN
              (SELECT id FROM prompts WHERE text = :p);
            """
        ),
        {"p": PROBE},
    )
    session.execute(
        text("DELETE FROM tasks WHERE brand_id IN (SELECT id FROM brands WHERE name = :p)"),
        {"p": PROBE},
    )
    session.execute(text("DELETE FROM prompts WHERE text = :p"), {"p": PROBE})
    session.execute(text("DELETE FROM brands WHERE name = :p"), {"p": PROBE})
    session.commit()


def _make_brand_task_run(db):
    """建 brand → prompt → task → run，外加一条 run_prompts / run_competitors 快照。"""
    from app.models import Brand, Prompt, Run, RunCompetitor, RunPrompt, Task

    brand = Brand(name=PROBE)
    db.add(brand)
    db.flush()
    prompt = Prompt(brand_id=brand.id, text=PROBE)
    db.add(prompt)
    db.flush()
    task = Task(brand_id=brand.id, name=PROBE)
    db.add(task)
    db.flush()
    run = Run(task_id=task.id)
    db.add(run)
    db.flush()
    db.add(RunPrompt(run_id=run.id, prompt_id=prompt.id, prompt_text=PROBE))
    # competitor_brand_id 刻意不设外键（快照），随便给个不存在的 id 也合法
    db.add(RunCompetitor(run_id=run.id, competitor_brand_id=999999, brand_name=PROBE))
    db.commit()
    return brand.id, prompt.id, task.id, run.id


def test_tables_exist(conn):
    names = set(sa_inspect(conn).get_table_names())
    for t in ("tasks", "runs", "run_prompts", "run_competitors"):
        assert t in names, f"缺表 {t}"


def test_crawl_jobs_has_nullable_run_id(conn):
    cols = {c["name"]: c for c in sa_inspect(conn).get_columns("crawl_jobs")}
    assert "run_id" in cols, "crawl_jobs 必须能指回它属于哪次运行"
    assert cols["run_id"]["nullable"] is True, (
        "必须可空 —— 迁移前已有的 job 没有 run，非空会让迁移直接失败"
    )


def test_run_has_no_status_column(conn):
    """状态由 job 派生，不落列。

    落了列就要有人维护它，而 job 状态在 worker 里变、run 状态在别处变，
    两者迟早不一致。不一致的状态列比没有更糟：它看起来权威。
    """
    cols = {c["name"] for c in sa_inspect(conn).get_columns("runs")}
    assert "status" not in cols


def test_delete_run_cascades_prompts_competitors_jobs(db):
    """删 Run 必须真的删掉子表，而不是把 crawl_jobs.run_id 静默置 NULL。

    CrawlJob 与 Run 之间没有声明 ORM relationship，级联完全交给数据库的
    ON DELETE CASCADE。这条测试守的正是「以后有人加了 relationship 却忘了
    passive_deletes=True」这个坑——run_id 可空，忘加的后果不是 IntegrityError
    500（那样至少会被立刻发现），而是 job 被静默改成孤儿，级联根本没发生。
    """
    from app.models import CrawlJob, Run, RunCompetitor, RunPrompt

    brand_id, prompt_id, task_id, run_id = _make_brand_task_run(db)
    job = CrawlJob(prompt_id=prompt_id, run_id=run_id, platform="deepseek", status="pending")
    db.add(job)
    db.commit()
    job_id = job.id

    run = db.get(Run, run_id)
    db.delete(run)
    db.commit()

    assert db.get(Run, run_id) is None
    assert db.get(CrawlJob, job_id) is None, "crawl_job 应随 run 级联删除，而不是 run_id 被置空"
    left_prompts = db.scalar(
        select(func.count()).select_from(RunPrompt).where(RunPrompt.run_id == run_id)
    )
    left_competitors = db.scalar(
        select(func.count()).select_from(RunCompetitor).where(RunCompetitor.run_id == run_id)
    )
    assert left_prompts == 0, "run_prompts 应随 run 级联删除"
    assert left_competitors == 0, "run_competitors 应随 run 级联删除"


def test_delete_task_cascades_runs(db):
    from app.models import Run, Task

    brand_id, prompt_id, task_id, run_id = _make_brand_task_run(db)

    task = db.get(Task, task_id)
    db.delete(task)
    db.commit()

    assert db.get(Task, task_id) is None
    assert db.get(Run, run_id) is None, "run 应随 task 级联删除"
