"""ApiKeyMiddleware 行为测试（不依赖数据库）。

关键约定：
- /v1/* 只认请求头，**不认 Cookie** —— 否则第三方站点能借浏览器 Cookie 发起 CSRF 写操作
- /qa/* 额外认 Cookie（浏览器加不了请求头），但 QA 页面全是 GET，只读
- /health 永远公开（部署脚本探针）
- API_KEY 为空 = 整体不校验（本机开发）
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import QA_COOKIE_NAME, ApiKeyMiddleware

KEY = "test-key-abc123"


def build_app() -> FastAPI:
    from app.api import qa as qa_router

    app = FastAPI()
    app.add_middleware(ApiKeyMiddleware)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/health/config")
    def health_config():
        return {"crawl_mode": "real"}

    @app.post("/v1/brands")
    def create_brand():
        return {"created": True}

    @app.get("/qa")
    def qa_home():
        return {"page": "qa"}

    # 真实的登录路由（只挑不碰数据库的三个）
    app.add_api_route("/qa/login", qa_router.qa_login_form, methods=["GET"])
    app.add_api_route("/qa/login", qa_router.qa_login, methods=["POST"])
    return app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEY", KEY)
    get_settings.cache_clear()
    yield TestClient(build_app())
    get_settings.cache_clear()


@pytest.fixture
def open_client(monkeypatch):
    monkeypatch.setenv("API_KEY", "")
    get_settings.cache_clear()
    yield TestClient(build_app())
    get_settings.cache_clear()


def test_health_is_public(client):
    assert client.get("/health").status_code == 200


def test_write_endpoint_rejected_without_key(client):
    r = client.post("/v1/brands")
    assert r.status_code == 401
    assert "X-API-Key" in r.json()["detail"]


def test_write_endpoint_rejected_with_wrong_key(client):
    r = client.post("/v1/brands", headers={"X-API-Key": "nope"})
    assert r.status_code == 401


def test_write_endpoint_accepts_header(client):
    assert client.post("/v1/brands", headers={"X-API-Key": KEY}).status_code == 200


def test_write_endpoint_accepts_bearer(client):
    r = client.post("/v1/brands", headers={"Authorization": f"Bearer {KEY}"})
    assert r.status_code == 200


def test_config_endpoint_is_not_public(client):
    """运行配置（crawl_mode 等）不该像原来那样挂在公开 /health 上。"""
    assert client.get("/health/config").status_code == 401
    assert client.get("/health/config", headers={"X-API-Key": KEY}).status_code == 200


def test_qa_accepts_cookie(client):
    client.cookies.set(QA_COOKIE_NAME, KEY, path="/qa")
    assert client.get("/qa").status_code == 200


def test_v1_ignores_cookie(client):
    """CSRF 防线：Cookie 对写接口无效。"""
    client.cookies.set(QA_COOKIE_NAME, KEY, path="/")
    assert client.post("/v1/brands").status_code == 401


def test_qa_html_request_redirects_to_login(client):
    r = client.get("/qa", headers={"Accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/qa/login"


def test_login_sets_cookie_and_grants_qa(client):
    r = client.post("/qa/login", data={"key": KEY}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/qa"
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "Path=/qa" in cookie
    assert client.get("/qa").status_code == 200


def test_login_rejects_wrong_key(client):
    r = client.post("/qa/login", data={"key": "wrong"}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/qa/login?bad=1"
    assert QA_COOKIE_NAME not in r.headers.get("set-cookie", "")


def test_key_never_appears_in_a_url(client):
    """密钥只走 POST body / 请求头，不进 query string（会落进访问日志与 Referer）。"""
    r = client.post("/qa/login", data={"key": KEY}, follow_redirects=False)
    assert KEY not in r.headers["location"]


def test_auth_disabled_when_key_empty(open_client):
    assert open_client.post("/v1/brands").status_code == 200
    assert open_client.get("/qa").status_code == 200
