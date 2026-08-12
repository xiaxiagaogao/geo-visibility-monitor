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


# ══════ 品牌 / 提问词 / counts 的收敛 ══════
#
# 上面四条验的是 task 与 run。但客户在界面上最先撞到的是**品牌列表**，
# 而它走的是另一条路：`list_brands` 不是靠 assert_*，是靠
# `visible_workspace_id` 把 workspace_id 参数**强制覆盖**掉。
#
# 这条路有个特点：**漏了也看不出来**。只要生产库里只有一个 workspace，
# 收敛与不收敛的返回结果一模一样 —— 这正是它必须用两个 workspace 的真库
# 来验、而不能靠肉眼在界面上核的原因。


def test_client_brand_list_scopes_to_workspace(db, two_workspaces):
    """不带参数时，客户只能拿到自己 workspace 的品牌。"""
    from app.api.brands import list_brands

    (brand1, _, _), (brand2, _, _) = two_workspaces
    out = list_brands(workspace_id=None, db=db, principal=_client(1))
    ids = {b.id for b in out.items}
    assert brand1.id in ids
    assert brand2.id not in ids


def test_client_cannot_widen_scope_by_passing_workspace_id(db, two_workspaces):
    """**这条是重点。** workspace_id 是个普通查询参数，客户改一个数字就能试。

    收敛必须是**强制覆盖**而不是「他没传就帮他填」——
    后者在他传了别人的 workspace_id 时会原样放行。
    """
    from app.api.brands import list_brands

    (brand1, _, _), (brand2, _, _) = two_workspaces
    out = list_brands(workspace_id=2, db=db, principal=_client(1))
    ids = {b.id for b in out.items}
    assert brand2.id not in ids, "客户传别人的 workspace_id 必须无效"
    assert brand1.id in ids, "而且要落回他自己的，不是返回空"


def test_operator_can_filter_by_workspace(db, two_workspaces):
    """反向用例：对运营来说 workspace_id 是个正常的筛选参数，不该被吃掉。

    只验「客户被挡住」的话，一个无条件忽略该参数的实现也能全绿。
    """
    from app.api.brands import list_brands
    from app.core.security import Principal

    operator = Principal(kind="user", role="operator", user_id=998)
    (brand1, _, _), (brand2, _, _) = two_workspaces
    ids = {b.id for b in list_brands(workspace_id=2, db=db, principal=operator).items}
    assert brand2.id in ids
    assert brand1.id not in ids


def test_client_cannot_see_other_workspace_brand(db, two_workspaces):
    from app.api.deps import assert_brand_visible

    (_, _, _), (brand2, _, _) = two_workspaces
    with pytest.raises(HTTPException) as exc:
        assert_brand_visible(db, _client(1), brand2.id)
    assert exc.value.status_code == 404, "必须是 404 —— 403 等于确认这条存在"


def test_client_prompt_list_scopes_to_workspace(db, two_workspaces):
    """提问词走的是第三条路（visible_brand_ids 展开），也要单独验。"""
    from app.api.prompts import list_prompts

    out = list_prompts(brand_id=None, active_only=False, db=db, principal=_client(1))
    texts = {p.text for p in out.items}
    assert f"{PROBE} q1" in texts
    assert f"{PROBE} q2" not in texts


def test_client_counts_on_other_workspace_brand_is_404(db, two_workspaces):
    """counts 的 brand_id 是必填的 —— 客户改一个数字就能查别家，必须逐个校验。"""
    from app.api.counts import get_counts

    (_, _, _), (brand2, _, _) = two_workspaces
    with pytest.raises(HTTPException) as exc:
        get_counts(brand_id=brand2.id, db=db, principal=_client(1))
    assert exc.value.status_code == 404
