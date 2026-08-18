"""``POST /v1/worker/environment`` 与 ``.../credentials``（P2-34 第 3 步）。

**这一步才是「节点不再需要 `DATABASE_URL`」的那一步。** 前两步只搬走了 job 的
领取与回传，而 crawler 还在直接往 `crawl_environments` 与 `crawl_credentials`
两张表写 —— 只要还有一处直连，库凭证就得留在那台大陆家宽的机器上。

分工是**纯函数留在节点、落库搬到 api**：

| 在节点算 | 为什么 |
|---|---|
| `inspect_storage_state` / `derive_status` | 要读 `storage_state` 文件，api 读不到 |
| `probe_exit_ip` | 要的是**这个节点**从哪儿出去的 |

| 在 api 算 | 为什么 |
|---|---|
| `compute_fingerprint` | 它定义「什么算同一种环境」。让节点自己算，版本一旦不齐就会造出幻影环境 |
| `checked_at` | 它是「多久没听到节点动静」的信号。用节点的时钟，钟一歪这个信号就说假话 |

行为档在 VPS 的一次性 postgres 里跑：

    GEO_TEST_DATABASE_URL="$DATABASE_URL" python -m pytest tests/test_worker_selfreport.py -q
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

TEST_DB = os.environ.get("GEO_TEST_DATABASE_URL")

PROBE = "__pytest_selfreport__"

behaviour = pytest.mark.skipif(
    not TEST_DB, reason="需要 GEO_TEST_DATABASE_URL 指向真实 Postgres"
)


def _purge(session) -> None:
    from sqlalchemy import text

    session.execute(
        text("UPDATE crawl_jobs SET environment_id = NULL WHERE environment_id IN "
             "(SELECT id FROM crawl_environments WHERE fingerprint LIKE :p)"),
        {"p": f"{PROBE}%"},
    )
    session.execute(
        text("DELETE FROM crawl_environments WHERE fingerprint LIKE :p"), {"p": f"{PROBE}%"}
    )
    session.execute(
        text("DELETE FROM crawl_credentials WHERE platform = :p"), {"p": "tongyi"}
    )
    session.commit()


@pytest.fixture
def db():
    from app.core.db import SessionLocal

    session = SessionLocal()
    try:
        _purge(session)
        yield session
    finally:
        session.rollback()
        _purge(session)
        session.close()


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.api.deps import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app, base_url="https://testserver")
    finally:
        app.dependency_overrides.pop(get_db, None)


ENV = {
    "node_label": f"{PROBE}-changsha",
    "exit_ip": "120.228.64.174",
    "timezone_id": "Asia/Shanghai",
    "crawl_mode": "real",
    "credential_region": "cn",
    "waf_kind": "huawei",
}


# ─────────────────────────────────────────────────────────────────────────
# 一、采集环境
# ─────────────────────────────────────────────────────────────────────────


@behaviour
def test_environment_returns_an_id_the_node_can_stamp_jobs_with(client, db):
    r = client.post("/v1/worker/environment", json=ENV)

    assert r.status_code == 200
    assert isinstance(r.json()["environment_id"], int)


@behaviour
def test_environment_stores_all_six_dimensions(client, db):
    from app.models import CrawlEnvironment

    env_id = client.post("/v1/worker/environment", json=ENV).json()["environment_id"]

    db.expire_all()
    row = db.get(CrawlEnvironment, env_id)
    assert row.node_label == ENV["node_label"]
    assert row.exit_ip == "120.228.64.174"
    assert row.timezone_id == "Asia/Shanghai"
    assert row.crawl_mode == "real"
    assert row.credential_region == "cn"
    assert row.waf_kind == "huawei"


@behaviour
def test_same_environment_reuses_one_row(client, db):
    """一行 = 一种环境。节点每 5 分钟报一次，堆行的话
    `SELECT DISTINCT environment_id` 那条「混了没有」的判据就废了。"""
    first = client.post("/v1/worker/environment", json=ENV).json()["environment_id"]
    second = client.post("/v1/worker/environment", json=ENV).json()["environment_id"]

    assert first == second


@behaviour
def test_a_changed_dimension_is_a_different_environment(client, db):
    """出口 IP 变了就是另一种环境 —— 那正是「跨 run 对比要小心」的时刻。"""
    first = client.post("/v1/worker/environment", json=ENV).json()["environment_id"]
    moved = client.post(
        "/v1/worker/environment", json=dict(ENV, exit_ip="36.157.231.164")
    ).json()["environment_id"]

    assert first != moved


@behaviour
def test_fingerprint_is_computed_server_side(client, db):
    """**指纹不听节点的。**

    `FINGERPRINT_FIELDS` 定义「什么算同一种环境」。让节点自己算并上报的话，
    节点与冷备一旦版本不齐，同一种环境会算出两个指纹 —— 造出一个幻影环境，
    而 P2-36 的告警会据此说「这次 run 混了两个出口」。**告警撒谎比没有告警更糟。**
    """
    from app.models import CrawlEnvironment
    from app.services.crawl_env import compute_fingerprint

    env_id = client.post(
        "/v1/worker/environment", json=dict(ENV, fingerprint="节点瞎编的指纹")
    ).json()["environment_id"]

    db.expire_all()
    assert db.get(CrawlEnvironment, env_id).fingerprint == compute_fingerprint(ENV)


@behaviour
def test_missing_dimension_does_not_collide_with_empty_string(client, db):
    """探不到 IP（None）和 IP 是空串，不能归成同一种环境。"""
    none_ip = client.post(
        "/v1/worker/environment", json=dict(ENV, exit_ip=None)
    ).json()["environment_id"]
    real_ip = client.post("/v1/worker/environment", json=ENV).json()["environment_id"]

    assert none_ip != real_ip


# ─────────────────────────────────────────────────────────────────────────
# 二、登录态健康度
# ─────────────────────────────────────────────────────────────────────────


CRED = {
    "platform": "tongyi",
    "status": "ok",
    "node_label": f"{PROBE}-changsha",
    "issuer_region": "unknown",
    "waf_kind": "none",
    "cookie_count": 12,
    "cookie_names": ["cna", "tfstk", "xlly_s"],
    "earliest_expiry": "2026-09-01T00:00:00+00:00",
    "file_mtime": "2026-08-16T10:00:00+00:00",
    "issues": [],
}


@behaviour
def test_credentials_writes_the_snapshot(client, db):
    from app.models import CrawlCredential

    r = client.post("/v1/worker/credentials", json={"items": [CRED]})

    assert r.status_code == 200
    db.expire_all()
    row = db.get(CrawlCredential, "tongyi")
    assert row.status == "ok"
    assert row.cookie_count == 12
    assert row.node_label == f"{PROBE}-changsha"


@behaviour
def test_credentials_upserts_instead_of_piling_up(client, db):
    """每平台一行 —— 节点每 5 分钟报一次，堆行的话这张表几天就没法看了。"""
    from sqlalchemy import func, select

    from app.models import CrawlCredential

    client.post("/v1/worker/credentials", json={"items": [CRED]})
    client.post("/v1/worker/credentials", json={"items": [dict(CRED, status="aging")]})

    db.expire_all()
    n = int(db.scalar(select(func.count()).select_from(CrawlCredential).where(
        CrawlCredential.platform == "tongyi"
    )))
    assert n == 1
    assert db.get(CrawlCredential, "tongyi").status == "aging"


@behaviour
def test_cookie_values_can_not_even_be_expressed(client, db):
    """**这条是红线**：库里永远只有 cookie 的名字，没有值。

    节点硬塞一个 `cookie_values` 字段进来也不该有任何效果 ——
    值是凭证本身，落进库就等于把登录态复制到一个没人当它是凭证的地方。
    """
    from app.models import CrawlCredential

    payload = dict(CRED, cookie_values=["secret-token-abc"], cookies=[{"name": "a", "value": "b"}])
    client.post("/v1/worker/credentials", json={"items": [payload]})

    db.expire_all()
    row = db.get(CrawlCredential, "tongyi")
    dumped = repr({c.name: getattr(row, c.name) for c in row.__table__.columns})
    assert "secret-token-abc" not in dumped
    assert row.cookie_names == ["cna", "tfstk", "xlly_s"]


@behaviour
def test_checked_at_is_server_time_not_node_time(client, db):
    """`checked_at` 是「多久没听到节点动静」的信号。

    用节点的时钟，钟一歪这个信号就说假话 —— 而 `BACKEND.md` §7.3 明写
    「checked_at 自己也是信号，太旧说明 crawler 没在跑」。所以服务端盖章。
    """
    from app.models import CrawlCredential

    before = datetime.now(timezone.utc) - timedelta(seconds=5)
    client.post(
        "/v1/worker/credentials",
        json={"items": [dict(CRED, checked_at="2001-01-01T00:00:00+00:00")]},
    )

    db.expire_all()
    assert db.get(CrawlCredential, "tongyi").checked_at >= before


@behaviour
def test_credentials_rejects_an_unknown_status(client, db):
    """乱写的 status 会直接出现在 /v1/health/credentials 的 overall 里。"""
    r = client.post(
        "/v1/worker/credentials", json={"items": [dict(CRED, status="probably-fine")]}
    )
    assert r.status_code == 422


@behaviour
def test_credentials_rejects_an_unknown_platform(client, db):
    """平台是主键 —— 写错一次就多一行永远清不掉的假平台。"""
    r = client.post(
        "/v1/worker/credentials", json={"items": [dict(CRED, platform="chatgpt")]}
    )
    assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────────
# 三、鉴权与路由（不需要数据库）
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "fn_name,path",
    [
        ("report_environment", "/v1/worker/environment"),
        ("report_credentials", "/v1/worker/credentials"),
    ],
)
def test_selfreport_routes_exist_and_require_write(fn_name, path):
    import inspect

    from app.api import worker as worker_api

    assert path in {r.path for r in worker_api.router.routes}
    assert "require_write" in inspect.getsource(getattr(worker_api, fn_name))
