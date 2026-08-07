"""跨租户 run_id + 自家 brand_id 拼接查询 —— 需要真实 Postgres。

Important 1（整体评审）的失败场景：workspace A 的客户拿自己名下的
brand_id，配上 workspace B 的 run_id 去调 /v1/counts。响应里
Prompt.brand_id == brand_id 与 CrawlJob.run_id == run_id 交集为空，
主/分母都会正确地返回 0；但改之前 competitor_ids 的 run_id 分支不带
brand 过滤，会把 workspace B 那次 run 快照里的 competitor_brand_id
原样吐出去 —— 一条跨租户的 run 存在性 + 竞品品牌 id 枚举通道。

两道校验都要钉住：
1. get_counts 路由层：run_id 不属于当前身份可见范围 → assert_run_visible 404
2. compute_counts 服务层：run_id 能看见、但不属于这个 brand_id → 404
"""
from __future__ import annotations

import os

import pytest
from fastapi import HTTPException

TEST_DB = os.environ.get("GEO_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DB, reason="需要 GEO_TEST_DATABASE_URL 指向真实 Postgres"
)

PROBE = "__pytest_run_brand_mismatch__"
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
def two_workspace_runs(db):
    """workspace 1、workspace 2 各一个品牌 + 一次 run（各自带一个竞品快照）。"""
    from app.models import Brand, CompetitorLink, Prompt, Task
    from app.services.tasks import create_run

    made = []
    for ws in (1, 2):
        own = Brand(name=f"{PROBE}_own{ws}", workspace_id=ws)
        rival = Brand(name=f"{PROBE}_rival{ws}", workspace_id=ws)
        db.add_all([own, rival])
        db.flush()
        db.add(CompetitorLink(brand_id=own.id, competitor_brand_id=rival.id))
        db.add(Prompt(brand_id=own.id, text=f"{PROBE} q{ws}", is_active=True))
        task = Task(
            brand_id=own.id, name=f"{PROBE} t{ws}", platforms=["deepseek"], samples=1
        )
        db.add(task)
        db.commit()
        run = create_run(db, task)
        made.append((own, rival, task, run))
    return made


def _client(workspace_id: int):
    from app.core.security import Principal

    return Principal(kind="user", role="client", user_id=999, workspace_id=workspace_id)


def test_compute_counts_rejects_run_from_other_brand(db, two_workspace_runs):
    """即使 run_id 对这个身份可见（比如 superadmin），brand_id 与 run 的
    所属品牌对不上时也必须 404 —— 这是 compute_counts 自己的防线，
    不依赖调用方有没有做过可见性校验。
    """
    from app.services.counts import compute_counts

    (own1, _, _, _), (own2, _, _, run2) = two_workspace_runs

    with pytest.raises(HTTPException) as exc:
        compute_counts(db, brand_id=own1.id, run_id=run2.id)
    assert exc.value.status_code == 404


def test_compute_counts_accepts_run_matching_its_own_brand(db, two_workspace_runs):
    """反向用例 —— 只验拒绝的话，一个永远 404 的实现也能全绿。"""
    from app.services.counts import compute_counts

    (own1, _, _, run1), _ = two_workspace_runs

    data = compute_counts(db, brand_id=own1.id, run_id=run1.id)
    assert data["brand_id"] == own1.id


def test_get_counts_route_rejects_cross_workspace_run_id(db, two_workspace_runs):
    """路由层：workspace 1 的客户拿自己的 brand_id 配 workspace 2 的 run_id。

    改之前这条会静默通过 assert_brand_visible（brand_id 是自己的），
    一路查进 compute_counts，把 workspace 2 的 run 快照里的竞品 id 吐出去。
    """
    from app.api.counts import get_counts

    (own1, _, _, _), (_, _, _, run2) = two_workspace_runs

    with pytest.raises(HTTPException) as exc:
        get_counts(
            brand_id=own1.id,
            platform=None,
            prompt_id=None,
            run_id=run2.id,
            date_from=None,
            date_to=None,
            group_by="none",
            include_fake=False,
            source=None,
            db=db,
            principal=_client(1),
        )
    assert exc.value.status_code == 404


def test_competitor_ids_no_longer_leak_cross_tenant_run_snapshot(db, two_workspace_runs):
    """根因复现：改之前 competitor_ids(db, brand_id, run_id) 的 run_id 分支
    完全不带 brand 过滤，任何 (brand_id, 别家 run_id) 组合都能读出那次 run
    快照里的 competitor_brand_id。现在必须在更上一层被 _assert_run_belongs_to_brand
    拦住，走不到 competitor_ids。
    """
    from app.services.counts import compute_counts

    (own1, _, _, _), (own2, rival2, _, run2) = two_workspace_runs

    with pytest.raises(HTTPException):
        compute_counts(db, brand_id=own1.id, run_id=run2.id)
    # 对照：run2 配自己的 brand（own2）能正常读出 rival2 —— 证明快照本身没坏，
    # 坏的是「不匹配的 brand/run 组合」被挡住了。
    data = compute_counts(db, brand_id=own2.id, run_id=run2.id)
    assert [c["brand_id"] for c in data["competitors"]] == [rival2.id]
