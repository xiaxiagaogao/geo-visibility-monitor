"""发起 run 时的口径冻结 —— 需要真实 Postgres。

守的是这个产品最核心的一条：两次 run 之间的差异必须是**表现变化**，
不能是**口径变化**。提问集决定分母，竞品集决定缺口清单与失分量，
两者都可改；不冻结的话，八月加一个竞品会重算七月的结论。
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import func, select

TEST_DB = os.environ.get("GEO_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DB, reason="需要 GEO_TEST_DATABASE_URL 指向真实 Postgres"
)

PROBE = "__pytest_task_run__"


@pytest.fixture
def db():
    from app.core.db import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def fixture_brand(db):
    """一个主品牌 + 一个竞品 + 两条启用提问 + 一条停用提问。"""
    from app.models import Brand, CompetitorLink, Prompt

    own = Brand(name=f"{PROBE}_own", workspace_id=1)
    rival = Brand(name=f"{PROBE}_rival", workspace_id=1)
    db.add_all([own, rival])
    db.flush()
    db.add(CompetitorLink(brand_id=own.id, competitor_brand_id=rival.id))
    db.add_all([
        Prompt(brand_id=own.id, text=f"{PROBE} q1", is_active=True),
        Prompt(brand_id=own.id, text=f"{PROBE} q2", is_active=True),
        Prompt(brand_id=own.id, text=f"{PROBE} q3", is_active=False),
    ])
    db.commit()
    yield own, rival
    for b in (own, rival):
        db.delete(db.get(Brand, b.id))
    db.commit()


def test_snapshot_freezes_prompts_and_competitors(db, fixture_brand):
    from app.models import Run, RunCompetitor, RunPrompt, Task
    from app.services.tasks import create_run

    own, rival = fixture_brand
    task = Task(brand_id=own.id, name=f"{PROBE} 周检", platforms=["deepseek"], samples=2)
    db.add(task)
    db.commit()

    run = create_run(db, task)

    prompts = db.scalars(select(RunPrompt).where(RunPrompt.run_id == run.id)).all()
    assert len(prompts) == 2, "只快照启用的提问词"
    assert all(p.prompt_text.startswith(PROBE) for p in prompts), "正文要一起存下来"

    rivals = db.scalars(
        select(RunCompetitor).where(RunCompetitor.run_id == run.id)
    ).all()
    assert [r.competitor_brand_id for r in rivals] == [rival.id]
    assert rivals[0].brand_name == f"{PROBE}_rival"

    assert db.get(Run, run.id).platforms == ["deepseek"]


def test_snapshot_survives_later_config_change(db, fixture_brand):
    """改配置不许改写历史 —— 这条是整个模型存在的理由。"""
    from app.models import Prompt, RunPrompt, Task
    from app.services.tasks import create_run

    own, rival = fixture_brand
    task = Task(brand_id=own.id, name=f"{PROBE} 周检", platforms=["deepseek"], samples=1)
    db.add(task)
    db.commit()
    run = create_run(db, task)

    # run 之后：加一条提问、改一条提问的正文
    newcomer = db.scalars(
        select(Prompt).where(Prompt.brand_id == own.id, Prompt.is_active.is_(True))
    ).first()
    newcomer.text = f"{PROBE} 改过的正文"
    db.add(Prompt(brand_id=own.id, text=f"{PROBE} q4", is_active=True))
    db.commit()

    assert db.scalar(
        select(func.count()).select_from(RunPrompt).where(RunPrompt.run_id == run.id)
    ) == 2, "新增提问不许进历史 run"
    texts = db.scalars(
        select(RunPrompt.prompt_text).where(RunPrompt.run_id == run.id)
    ).all()
    assert f"{PROBE} 改过的正文" not in texts, "改正文不许改写历史 run"


def test_jobs_are_attached_to_run(db, fixture_brand):
    from app.models import CrawlJob, Task
    from app.services.tasks import create_run

    own, _ = fixture_brand
    task = Task(brand_id=own.id, name=f"{PROBE} 周检", platforms=["deepseek"], samples=3)
    db.add(task)
    db.commit()
    run = create_run(db, task)

    jobs = db.scalars(select(CrawlJob).where(CrawlJob.run_id == run.id)).all()
    assert len(jobs) == 2 * 1 * 3, "2 条启用提问 × 1 平台 × 3 采样"
    assert {j.sample_index for j in jobs} == {1, 2, 3}


def test_empty_prompt_set_creates_no_jobs(db, fixture_brand):
    """提问集为空时不能静默建一个空 run 就报成功 —— derive_run_status 会给 empty。"""
    from app.models import CrawlJob, Prompt, Task
    from app.services.tasks import create_run

    own, _ = fixture_brand
    db.query(Prompt).filter(Prompt.brand_id == own.id).update({"is_active": False})
    db.commit()

    task = Task(brand_id=own.id, name=f"{PROBE} 空集", platforms=["deepseek"], samples=2)
    db.add(task)
    db.commit()
    run = create_run(db, task)

    assert db.scalars(select(CrawlJob).where(CrawlJob.run_id == run.id)).all() == []
