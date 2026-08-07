"""跨 workspace 越权 —— 需要真实 Postgres。

结构测试（test_task_rbac.py）只能验「代码里有没有调那个函数」，
验不了「真跨查时到底返回什么」。这一条补上后者。
"""
from __future__ import annotations

import os

import pytest
from fastapi import HTTPException

TEST_DB = os.environ.get("GEO_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DB, reason="需要 GEO_TEST_DATABASE_URL 指向真实 Postgres"
)

PROBE = "__pytest_rbac__"


def _purge(session) -> None:
    """按外键顺序清理，不依赖被测的级联行为。"""
    from sqlalchemy import text

    p = f"{PROBE}%"
    for sql in (
        "DELETE FROM crawl_jobs WHERE prompt_id IN (SELECT id FROM prompts WHERE text LIKE :p)",
        "DELETE FROM run_prompts WHERE run_id IN (SELECT r.id FROM runs r JOIN tasks t ON t.id = r.task_id JOIN brands b ON b.id = t.brand_id WHERE b.name LIKE :p)",
        "DELETE FROM run_competitors WHERE run_id IN (SELECT r.id FROM runs r JOIN tasks t ON t.id = r.task_id JOIN brands b ON b.id = t.brand_id WHERE b.name LIKE :p)",
        "DELETE FROM runs WHERE task_id IN (SELECT t.id FROM tasks t JOIN brands b ON b.id = t.brand_id WHERE b.name LIKE :p)",
        "DELETE FROM tasks WHERE brand_id IN (SELECT id FROM brands WHERE name LIKE :p)",
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
def two_workspaces(db):
    """workspace 1 和 workspace 2 各一个品牌、各一个任务、各一次运行。"""
    from app.models import Brand, Prompt, Task
    from app.services.tasks import create_run

    made = []
    for ws in (1, 2):
        brand = Brand(name=f"{PROBE}_ws{ws}", workspace_id=ws)
        db.add(brand)
        db.flush()
        db.add(Prompt(brand_id=brand.id, text=f"{PROBE} q{ws}", is_active=True))
        task = Task(
            brand_id=brand.id, name=f"{PROBE} t{ws}", platforms=["deepseek"], samples=1
        )
        db.add(task)
        db.commit()
        made.append((brand, task, create_run(db, task)))
    return made


def _client(workspace_id: int):
    """workspace 受限的客户身份。"""
    from app.core.security import Principal

    return Principal(
        kind="user", role="client", user_id=999, workspace_id=workspace_id
    )


def test_client_cannot_see_other_workspace_task(db, two_workspaces):
    from app.api.deps import assert_task_visible

    (_, _, _), (_, task2, _) = two_workspaces
    with pytest.raises(HTTPException) as exc:
        assert_task_visible(db, _client(1), task2.id)
    assert exc.value.status_code == 404, "必须是 404 —— 403 等于确认这条存在"


def test_client_cannot_see_other_workspace_run(db, two_workspaces):
    from app.api.deps import assert_run_visible

    (_, _, _), (_, _, run2) = two_workspaces
    with pytest.raises(HTTPException) as exc:
        assert_run_visible(db, _client(1), run2.id)
    assert exc.value.status_code == 404


def test_client_can_see_own_task(db, two_workspaces):
    """反向用例 —— 只验「拒绝」不验「放行」的话，一个永远抛 404 的实现也能全绿。"""
    from app.api.deps import assert_task_visible

    (_, task1, _), _ = two_workspaces
    assert_task_visible(db, _client(1), task1.id)  # 不抛即通过


def test_visible_task_ids_scopes_to_workspace(db, two_workspaces):
    from app.api.deps import visible_task_ids

    (_, task1, _), (_, task2, _) = two_workspaces
    ids = visible_task_ids(db, _client(1))
    assert task1.id in ids
    assert task2.id not in ids
