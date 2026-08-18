"""``POST /v1/worker/lease`` —— 领 job（P2-34 第 1 步）。

**交接文档写的是 GET，这里是 POST**，理由见文件末尾
``test_lease_cannot_be_driven_by_cookie_alone``：领取会改状态。

采集节点将来不碰数据库，改成来这里领任务。这一档钉的是**领取那一刻**的三件事：

1. 领到的 payload **自带 prompt 正文与别名** —— 节点没有数据库，查不到它们；
2. 领到就标 ``running``，**同一条不会被领第二次**（多节点安全的可观察形态）；
3. 退避中的 job（``next_attempt_at`` 在未来）**领不走** —— P2-16 的闸门不能因为
   换了入口就失效。

鉴权那一条不需要数据库，单独一组放在文件末尾。

行为档在 VPS 的一次性 postgres 里跑：

    GEO_TEST_DATABASE_URL="$DATABASE_URL" python -m pytest tests/test_worker_lease.py -q
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

TEST_DB = os.environ.get("GEO_TEST_DATABASE_URL")

PROBE = "__pytest_lease__"


# ─────────────────────────────────────────────────────────────────────────
# 一、领取行为（需要真库）
# ─────────────────────────────────────────────────────────────────────────

behaviour = pytest.mark.skipif(
    not TEST_DB, reason="需要 GEO_TEST_DATABASE_URL 指向真实 Postgres"
)


def _purge(session) -> None:
    """按外键顺序清干净，不依赖级联行为。"""
    from sqlalchemy import text

    p = f"{PROBE}%"
    for sql in (
        "DELETE FROM crawl_jobs WHERE prompt_id IN (SELECT id FROM prompts WHERE text LIKE :p)",
        "DELETE FROM prompts WHERE text LIKE :p",
        "DELETE FROM brand_aliases WHERE brand_id IN (SELECT id FROM brands WHERE name LIKE :p)",
        "DELETE FROM brands WHERE name LIKE :p",
    ):
        session.execute(text(sql), {"p": p})
    session.commit()


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


@pytest.fixture
def pending_job(db):
    """一条 pending 的 job，带品牌别名 —— 别名要能跟着 payload 一起下发。"""
    from app.models import Brand, BrandAlias, CrawlJob, Prompt

    brand = Brand(name=f"{PROBE}_安踏", name_en="ANTA", workspace_id=1)
    db.add(brand)
    db.flush()
    db.add(BrandAlias(brand_id=brand.id, alias="安踏体育"))
    prompt = Prompt(brand_id=brand.id, text=f"{PROBE} 国产运动鞋有哪些值得买？", is_active=True)
    db.add(prompt)
    db.flush()
    job = CrawlJob(prompt_id=prompt.id, platform="tongyi", status="pending", sample_index=3)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@behaviour
def test_lease_payload_carries_everything_the_node_needs(client, db, pending_job):
    """节点没有数据库 —— prompt 正文与别名必须随 payload 下发，否则它拼不出提问。"""
    body = client.post("/v1/worker/lease", params={"batch_size": 5}).json()

    got = [j for j in body["jobs"] if j["job_id"] == pending_job.id]
    assert len(got) == 1
    item = got[0]
    assert item["platform"] == "tongyi"
    assert item["sample_index"] == 3
    assert item["prompt_text"] == f"{PROBE} 国产运动鞋有哪些值得买？"
    assert set(item["brand_names"]) == {f"{PROBE}_安踏", "ANTA", "安踏体育"}


@behaviour
def test_lease_marks_job_running(client, db, pending_job):
    client.post("/v1/worker/lease", params={"batch_size": 5})

    db.expire_all()
    assert db.get(type(pending_job), pending_job.id).status == "running"


@behaviour
def test_lease_never_hands_out_the_same_job_twice(client, db, pending_job):
    """多节点安全的可观察形态：领过一次之后，同一条 job 不会再出现。"""
    first = client.post("/v1/worker/lease", params={"batch_size": 5}).json()
    second = client.post("/v1/worker/lease", params={"batch_size": 5}).json()

    assert pending_job.id in [j["job_id"] for j in first["jobs"]]
    assert pending_job.id not in [j["job_id"] for j in second["jobs"]]


@behaviour
def test_lease_skips_jobs_still_backing_off(client, db, pending_job):
    """P2-16 的退避闸门不能因为换了入口就失效 —— 它挡的是 pending 但没到点的 job。"""
    pending_job.next_attempt_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    db.commit()

    body = client.post("/v1/worker/lease", params={"batch_size": 5}).json()

    assert pending_job.id not in [j["job_id"] for j in body["jobs"]]


@behaviour
def test_lease_stamps_environment_id(client, db, pending_job):
    """P2-36：环境在**领取那一刻**打上。节点自报 environment_id，语义不变。"""
    from app.models import CrawlEnvironment

    env = CrawlEnvironment(fingerprint=f"{PROBE}|1.2.3.4|Asia/Shanghai|real|cn|huawei")
    db.add(env)
    db.commit()
    db.refresh(env)

    try:
        client.post(
            "/v1/worker/lease", params={"batch_size": 5, "environment_id": env.id}
        )
        db.expire_all()
        assert db.get(type(pending_job), pending_job.id).environment_id == env.id
    finally:
        from sqlalchemy import text

        db.execute(
            text("UPDATE crawl_jobs SET environment_id = NULL WHERE environment_id = :e"),
            {"e": env.id},
        )
        db.execute(text("DELETE FROM crawl_environments WHERE id = :e"), {"e": env.id})
        db.commit()


@behaviour
def test_lease_returns_empty_list_when_nothing_pending(client, db):
    """没活干是常态，不是错误 —— 节点每几秒问一次。"""
    from sqlalchemy import text

    db.execute(text("UPDATE crawl_jobs SET status = 'success' WHERE status = 'pending'"))
    db.commit()

    r = client.post("/v1/worker/lease", params={"batch_size": 5})
    assert r.status_code == 200
    assert r.json()["jobs"] == []


@pytest.fixture
def client(db):
    """真 app + 真库；``get_db`` 换成测试会话，好在同一个事务里看结果。"""
    from fastapi.testclient import TestClient

    from app.api.deps import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app, base_url="https://testserver")
    finally:
        app.dependency_overrides.pop(get_db, None)


# ─────────────────────────────────────────────────────────────────────────
# 二、鉴权（不需要数据库）
# ─────────────────────────────────────────────────────────────────────────
#
# 2026-08-18 拍板：**worker 复用现有 X-API-Key**，不另发一把。
# 代价写在 BACKEND.md §7.6 —— 采集节点持有的是超管等价凭证，所以 P2-34 的收益
# 是「只走 HTTPS 出站 + 截图能回来 + 天然多节点」，**不含**「缩小凭证权限面」。
# 这里钉住的是最起码的那条：它绝不能是公开端点。


def test_lease_is_not_public(monkeypatch):
    """没带 Key 时中间件就该挡下 —— 路由与数据库都不该被碰到。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import worker as worker_api
    from app.api.deps import get_db
    from app.core.config import get_settings
    from app.core.security import ApiKeyMiddleware

    monkeypatch.setenv("API_KEY", "test-key-abc123")
    get_settings.cache_clear()

    def _explode():
        raise AssertionError("未认证的请求不该走到数据库")

    app = FastAPI()
    app.add_middleware(ApiKeyMiddleware)
    app.include_router(worker_api.router)
    app.dependency_overrides[get_db] = _explode
    try:
        r = TestClient(app, base_url="https://testserver").post("/v1/worker/lease")
        assert r.status_code == 401
    finally:
        get_settings.cache_clear()


def test_lease_requires_write_role():
    """客户账号是纯只读 —— 领 job 是写操作（它会把 job 标成 running）。"""
    import inspect

    from app.api import worker as worker_api

    assert "require_write" in inspect.getsource(worker_api.lease_jobs)


def test_lease_cannot_be_driven_by_cookie_alone(monkeypatch):
    """**领 job 是写操作，所以它不能是 GET。**

    中间件对**安全方法**认 `geo_qa_key` Cookie（`<img src>` 要靠它显示证据截图），
    而 Cookie 会被第三方站点诱导带上。领取会把 job 标成 ``running``：跨站打一发
    就能让一批 job 空转到 600 秒后被僵死回收成 failed，攻击方连响应都不用读。

    本仓的红线是「所有会改状态的路由都是 POST/PUT/PATCH/DELETE」
    （`core/security.py` 模块 docstring，`test_security.py` 逐方法钉着）。
    lease 在交接文档里写的是 GET，**这里按红线改成 POST** —— 它确实会改状态。
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import worker as worker_api
    from app.api.deps import get_db
    from app.core.config import get_settings
    from app.core.security import QA_COOKIE_NAME, ApiKeyMiddleware

    key = "test-key-abc123"
    monkeypatch.setenv("API_KEY", key)
    get_settings.cache_clear()

    def _explode():
        raise AssertionError("Cookie 身份不该走到数据库")

    app = FastAPI()
    app.add_middleware(ApiKeyMiddleware)
    app.include_router(worker_api.router)
    app.dependency_overrides[get_db] = _explode
    try:
        client = TestClient(app, base_url="https://testserver")
        client.cookies.set(QA_COOKIE_NAME, key, path="/")
        assert client.get("/v1/worker/lease").status_code == 405
        assert client.post("/v1/worker/lease").status_code == 401
    finally:
        get_settings.cache_clear()
