"""登录态健康度落库与出口（P2-07）—— 需要真实 Postgres。

判级规则本身在 `test_credential_health.py` 里测（纯函数，本机可跑）。
这里钉三件事：真的写进了 `crawl_credentials`、**值绝不落库**、以及端点的口径。

在 VPS 的 api 容器里跑：

    GEO_TEST_DATABASE_URL="$DATABASE_URL" python -m pytest tests/test_credential_report.py -q
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

TEST_DB = os.environ.get("GEO_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DB, reason="需要 GEO_TEST_DATABASE_URL 指向真实 Postgres"
)

SECRET = "SECRET-VALUE-绝不该出现在数据库里"


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

    # **两个平台都要清** —— 只清一个会让「表空了」的用例永远看到残留行
    session.execute(text("DELETE FROM crawl_credentials"))
    session.commit()


def _settings(tmp_path, cookies, *, region="cn", max_age=14, mtime=None):
    """造一份 storage_state 与指向它的 Settings。"""
    from app.core.config import Settings

    p = tmp_path / "storage_state.json"
    p.write_text(
        json.dumps({"cookies": [
            {"name": n, "domain": "chat.deepseek.com", "expires": e, "value": SECRET}
            for n, e in cookies
        ], "origins": []}),
        encoding="utf-8",
    )
    if mtime:
        os.utime(p, (mtime.timestamp(), mtime.timestamp()))
    return Settings(
        deepseek_storage_state=str(p),
        crawl_expected_credential_region=region,
        crawl_credential_max_age_days=max_age,
        crawl_node_label="pytest-node",
    )


def test_report_writes_a_row(db, tmp_path):
    from app.models import CrawlCredential
    from app.services.credential_health import report_credentials

    exp = int((datetime.now(timezone.utc) + timedelta(days=300)).timestamp())
    out = report_credentials(db, _settings(tmp_path, [("HWWAFSESID", 0), ("smidV2", exp)]))

    # 返回值里必须带 issuer_region / waf_kind —— **P2-36 的环境指纹靠它们**，
    # 而它们正是这次检查刚算出来的。少了就得再读一遍文件
    ds = next(r for r in out if r["platform"] == "deepseek")
    assert ds == {
        "platform": "deepseek", "status": "ok", "issues": [],
        "issuer_region": "cn", "waf_kind": "huawei",
    }
    # 豆包没配路径 → missing，且**提示里必须是它自己的变量名**。
    # 这里原先写死 DEEPSEEK_STORAGE_STATE，会把人指去配错的环境变量
    doubao = next(r for r in out if r["platform"] == "doubao")
    assert doubao["status"] == "missing"
    assert "DOUBAO_STORAGE_STATE" in doubao["issues"][0]
    assert "DEEPSEEK" not in doubao["issues"][0], "写死别的平台变量名会把人指去配错的地方"
    row = db.get(CrawlCredential, "deepseek")
    assert row.status == "ok"
    assert row.issuer_region == "cn" and row.waf_kind == "huawei"
    assert row.node_label == "pytest-node"
    assert row.cookie_count == 2


def test_cookie_values_never_reach_the_database(db, tmp_path):
    """**这条是硬规矩。** 值是凭证本身，落进库就等于把登录态复制了一份
    到一个没人当它是凭证的地方。"""
    from sqlalchemy import text
    from app.services.credential_health import report_credentials

    report_credentials(db, _settings(tmp_path, [("HWWAFSESID", 0)]))

    dumped = db.execute(
        text("SELECT row_to_json(c)::text FROM crawl_credentials c WHERE platform='deepseek'")
    ).scalar()
    assert SECRET not in dumped
    assert "HWWAFSESID" in dumped   # 名字留着（接新平台时要靠它认 WAF）


def test_the_2026_08_15_incident_would_have_been_visible(db, tmp_path):
    """从新加坡导出、AWS WAF、已过期 —— 这正是当时那份登录态的形状。"""
    from app.models import CrawlCredential
    from app.services.credential_health import report_credentials

    expired = int((datetime.now(timezone.utc) - timedelta(days=11)).timestamp())
    report_credentials(db, _settings(tmp_path, [("aws-waf-token", expired), ("ds_session_id", 0)]))

    row = db.get(CrawlCredential, "deepseek")
    assert row.status == "mismatch"
    assert row.issuer_region == "overseas"
    assert len(row.issues) == 2   # 签发地 + 已过期，两个都列出来


def test_report_upserts_instead_of_piling_up(db, tmp_path):
    """每个平台一行。堆历史会让「现在健不健康」要先排序才知道。"""
    from sqlalchemy import text
    from app.services.credential_health import report_credentials

    s = _settings(tmp_path, [("HWWAFSESID", 0)])
    report_credentials(db, s)
    report_credentials(db, s)

    n = db.execute(
        text("SELECT count(*) FROM crawl_credentials WHERE platform='deepseek'")
    ).scalar()
    assert n == 1


def test_report_survives_a_missing_file(db, tmp_path):
    """健康检查自己不能成为故障源 —— 它跑在采集循环里。"""
    from app.core.config import Settings
    from app.models import CrawlCredential
    from app.services.credential_health import report_credentials

    out = report_credentials(db, Settings(deepseek_storage_state="/nope/missing.json"))
    assert next(r for r in out if r["platform"] == "deepseek")["status"] == "missing"
    assert db.get(CrawlCredential, "deepseek").status == "missing"


# ------------------------------------------------------------------ 端点


def test_endpoint_reports_unreported_when_empty(db):
    """一条都没有 ≠ 健康。crawler 从没上报过时报 ok，
    会让这个端点变成一句安慰话。"""
    from app.api.health_credentials import get_credential_health

    _purge(db)
    out = get_credential_health(db=db, _=None)
    assert out.overall == "unreported" and out.items == []


def test_endpoint_surfaces_worst_status_and_last_success(db, tmp_path):
    from app.api.health_credentials import get_credential_health
    from app.services.credential_health import report_credentials

    expired = int((datetime.now(timezone.utc) - timedelta(days=11)).timestamp())
    report_credentials(db, _settings(tmp_path, [("aws-waf-token", expired)]))

    out = get_credential_health(db=db, _=None)
    # 豆包那行是 missing（没配路径），比 mismatch 更严重 ——
    # overall 取最严重的那个，所以这里断言的是 deepseek 那一行本身
    assert out.overall in ("missing", "mismatch")
    item = next(i for i in out.items if i.platform == "deepseek")
    assert item.issuer_region == "overseas"
    assert SECRET not in item.model_dump_json()


def test_endpoint_requires_write_role():
    """客户不该看到我们的凭证状态：既是运维内情，也暴露采集拓扑。"""
    import inspect as _inspect
    from app.api import health_credentials as api

    src = _inspect.getsource(api.get_credential_health)
    assert "require_write" in src
