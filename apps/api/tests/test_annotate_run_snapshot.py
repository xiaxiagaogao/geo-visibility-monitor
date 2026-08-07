"""annotate.py 的 mention 抽取按 run 冻结的竞品集走 —— 需要真实 Postgres。

复现 Important 2（整体评审）的失败场景：run 创建时冻结竞品集 [rival]。
run 建好之后，有人整体替换了品牌的竞品配置（PUT /v1/brands/{id}/competitors
的语义）——rival 换成 newcomer。这批 job 完成时触发的 annotate_response
如果还读「当时的活配置」，会给 newcomer 生成 Mention 行、漏掉 rival，
和 /v1/counts?run_id= 用 RunCompetitor 快照算出的 track_ids（仍是
[own, rival]）对不上。
"""
from __future__ import annotations

import os

import pytest

TEST_DB = os.environ.get("GEO_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DB, reason="需要 GEO_TEST_DATABASE_URL 指向真实 Postgres"
)

PROBE = "__pytest_annotate_run_snapshot__"
PROBE_LIKE = f"{PROBE}%"


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


def _purge(session) -> None:
    from sqlalchemy import text

    like = {"p": PROBE_LIKE}
    for sql in (
        """
        DELETE FROM mentions WHERE response_id IN (
          SELECT rr.id FROM raw_responses rr
          JOIN crawl_jobs cj ON cj.id = rr.job_id
          JOIN prompts p ON p.id = cj.prompt_id
          WHERE p.text LIKE :p
        );
        """,
        """
        DELETE FROM raw_responses WHERE job_id IN (
          SELECT id FROM crawl_jobs WHERE prompt_id IN
            (SELECT id FROM prompts WHERE text LIKE :p)
        );
        """,
        """
        DELETE FROM crawl_jobs WHERE prompt_id IN
          (SELECT id FROM prompts WHERE text LIKE :p);
        """,
        """
        DELETE FROM run_prompts WHERE run_id IN (
          SELECT r.id FROM runs r
          JOIN tasks t ON t.id = r.task_id
          JOIN brands b ON b.id = t.brand_id
          WHERE b.name LIKE :p
        );
        """,
        """
        DELETE FROM run_competitors WHERE run_id IN (
          SELECT r.id FROM runs r
          JOIN tasks t ON t.id = r.task_id
          JOIN brands b ON b.id = t.brand_id
          WHERE b.name LIKE :p
        );
        """,
        """
        DELETE FROM runs WHERE task_id IN (
          SELECT t.id FROM tasks t
          JOIN brands b ON b.id = t.brand_id
          WHERE b.name LIKE :p
        );
        """,
        "DELETE FROM tasks WHERE brand_id IN (SELECT id FROM brands WHERE name LIKE :p);",
        """
        DELETE FROM competitor_links WHERE brand_id IN
          (SELECT id FROM brands WHERE name LIKE :p)
          OR competitor_brand_id IN
          (SELECT id FROM brands WHERE name LIKE :p);
        """,
        "DELETE FROM prompts WHERE text LIKE :p;",
        "DELETE FROM brands WHERE name LIKE :p;",
    ):
        session.execute(text(sql), like)
    session.commit()


@pytest.fixture
def fixture_run(db):
    """own + rival(冻结进 run 快照) + newcomer(run 建好之后才顶替 rival)。"""
    from app.models import Brand, CompetitorLink, Prompt, Task
    from app.services.tasks import create_run

    own = Brand(name=f"{PROBE}_own", workspace_id=1)
    rival = Brand(name=f"{PROBE}_rival", workspace_id=1)
    db.add_all([own, rival])
    db.flush()
    db.add(CompetitorLink(brand_id=own.id, competitor_brand_id=rival.id))
    db.add(Prompt(brand_id=own.id, text=f"{PROBE} q1", is_active=True))
    db.commit()

    task = Task(brand_id=own.id, name=f"{PROBE} 周检", platforms=["deepseek"], samples=1)
    db.add(task)
    db.commit()
    run = create_run(db, task)  # 冻结 [rival] 进 run_competitors

    # run 建好之后：整体替换竞品配置，rival 换成 newcomer
    newcomer = Brand(name=f"{PROBE}_newcomer", workspace_id=1)
    db.add(newcomer)
    db.flush()
    db.query(CompetitorLink).filter(CompetitorLink.brand_id == own.id).delete()
    db.add(CompetitorLink(brand_id=own.id, competitor_brand_id=newcomer.id))
    db.commit()

    return own, rival, newcomer, run


def test_target_brand_ids_with_run_id_reads_frozen_snapshot(db, fixture_run):
    from app.services.annotate import target_brand_ids

    own, rival, newcomer, run = fixture_run
    ids = target_brand_ids(db, own.id, run.id)
    assert ids[0] == own.id, "本品必须仍是第一个"
    assert rival.id in ids, "run 冻结时的竞品必须还在"
    assert newcomer.id not in ids, "run 之后才顶替进来的竞品不该混进这次 run 的抽取范围"


def test_target_brand_ids_without_run_id_reads_current_config(db, fixture_run):
    """ad-hoc job（没有 run 归属）行为必须不变：退回当前 CompetitorLink。"""
    from app.services.annotate import target_brand_ids

    own, rival, newcomer, run = fixture_run
    ids = target_brand_ids(db, own.id, None)
    assert ids[0] == own.id
    assert newcomer.id in ids, "无 run 归属时必须读当前配置"
    assert rival.id not in ids, "当前配置已经不含 rival"


def test_annotate_response_generates_mentions_for_frozen_competitors_only(db, fixture_run):
    """行为级根因验证：job 挂在 run 下时，即使正文同时提到 rival 和 newcomer，
    annotate_response 也只该给 run 冻结集合里的品牌（own, rival）生成 Mention 行,
    newcomer 这条不该有 —— 它是 run 建好之后才加入配置的。
    """
    from sqlalchemy import select

    from app.models import CrawlJob, Mention, Prompt, RawResponse
    from app.services.annotate import annotate_response

    own, rival, newcomer, run = fixture_run
    prompt_id = db.scalar(select(Prompt.id).where(Prompt.brand_id == own.id))
    job = CrawlJob(prompt_id=prompt_id, run_id=run.id, platform="deepseek", status="done")
    db.add(job)
    db.flush()
    resp = RawResponse(
        job_id=job.id,
        platform="deepseek",
        prompt_text=f"{PROBE} q1",
        full_text=(
            f"{PROBE} 综合来看，{own.name} 和 {rival.name} 都提到了，"
            f"{newcomer.name} 这次也被顺带提了一句，仅供参考。"
        ),
    )
    db.add(resp)
    db.commit()

    annotate_response(db, resp.id)

    mentions = db.scalars(select(Mention).where(Mention.response_id == resp.id)).all()
    brand_ids = {m.brand_id for m in mentions}
    assert brand_ids == {own.id, rival.id}, (
        "只应该给 run 冻结集合里的品牌生成 Mention 行；"
        f"newcomer(id={newcomer.id}) 不该出现，即便正文提到了它"
    )
    by_brand = {m.brand_id: m for m in mentions}
    assert by_brand[rival.id].mentioned is True, "rival 在正文里确实出现了，应该被标记命中"
