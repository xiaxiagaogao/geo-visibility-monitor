"""级联删除 —— 需要真实 Postgres。

在 VPS 的 api 容器里跑：

    docker exec -w /app/apps/api -e PYTHONPATH=. \
      -e GEO_TEST_DATABASE_URL="$DATABASE_URL" geo-api python -m pytest tests/ -q

背景：ORM 关系没配 passive_deletes 时，SQLAlchemy 删父行前会先
``UPDATE 子表 SET 外键=NULL``，而这些外键列都是 NOT NULL，于是
``DELETE /v1/brands/{id}``、``DELETE /v1/prompts/{id}`` 对有子行的记录直接 500。
数据库层的 ON DELETE CASCADE 根本没机会生效。
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import func, select

TEST_DB = os.environ.get("GEO_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DB, reason="需要 GEO_TEST_DATABASE_URL 指向真实 Postgres"
)

PROBE = "__pytest_cascade__"


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
    session.execute(text("DELETE FROM prompts WHERE text = :p"), {"p": PROBE})
    session.execute(text("DELETE FROM brands WHERE name = :p"), {"p": PROBE})
    session.commit()


def _make_brand_with_prompt(db):
    from app.models import Brand, Prompt

    brand = Brand(name=PROBE)
    db.add(brand)
    db.flush()
    prompt = Prompt(brand_id=brand.id, text=PROBE)
    db.add(prompt)
    db.commit()
    return brand.id, prompt.id


def test_delete_brand_with_prompts(db):
    from app.models import Brand, Prompt
    from app.services.brands import delete_brand

    brand_id, prompt_id = _make_brand_with_prompt(db)

    delete_brand(db, brand_id)

    assert db.get(Brand, brand_id) is None
    assert db.get(Prompt, prompt_id) is None, "prompt 应随品牌级联删除"


def test_delete_brand_with_aliases(db):
    from app.models import Brand, BrandAlias
    from app.services.brands import delete_brand

    brand = Brand(name=PROBE)
    db.add(brand)
    db.flush()
    db.add(BrandAlias(brand_id=brand.id, alias=PROBE))
    db.commit()
    brand_id = brand.id

    delete_brand(db, brand_id)

    assert db.get(Brand, brand_id) is None
    left = db.scalar(
        select(func.count()).select_from(BrandAlias).where(BrandAlias.brand_id == brand_id)
    )
    assert left == 0


def test_delete_prompt_with_jobs(db):
    from app.models import CrawlJob, Prompt
    from app.services.prompts import delete_prompt

    brand_id, prompt_id = _make_brand_with_prompt(db)
    db.add(CrawlJob(prompt_id=prompt_id, platform="deepseek", status="pending"))
    db.commit()

    delete_prompt(db, prompt_id)

    assert db.get(Prompt, prompt_id) is None
    left = db.scalar(
        select(func.count()).select_from(CrawlJob).where(CrawlJob.prompt_id == prompt_id)
    )
    assert left == 0, "crawl_job 应随 prompt 级联删除"


def test_delete_brand_cascades_all_the_way_down(db):
    """品牌 → prompt → job → response → mention/citation 全链路。"""
    from app.models import Brand, Citation, CrawlJob, Mention, RawResponse
    from app.services.brands import delete_brand

    brand_id, prompt_id = _make_brand_with_prompt(db)
    job = CrawlJob(prompt_id=prompt_id, platform="deepseek", status="success")
    db.add(job)
    db.flush()
    resp = RawResponse(
        job_id=job.id, platform="deepseek", prompt_text=PROBE, full_text=PROBE
    )
    db.add(resp)
    db.flush()
    db.add(Mention(response_id=resp.id, brand_id=brand_id, mentioned=False, mention_type="none"))
    db.add(Citation(response_id=resp.id, url="https://example.com", domain="example.com"))
    db.commit()
    resp_id = resp.id

    delete_brand(db, brand_id)

    assert db.get(Brand, brand_id) is None
    assert db.get(RawResponse, resp_id) is None
    for model, col in ((Mention, Mention.response_id), (Citation, Citation.response_id)):
        assert db.scalar(select(func.count()).select_from(model).where(col == resp_id)) == 0
