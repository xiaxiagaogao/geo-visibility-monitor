"""ApiKeyMiddleware 行为测试（不依赖数据库）。

分界线是 **HTTP 方法**，不是路径（F0a）：

- 请求头认证：任何方法都接受
- Cookie 认证：**只对 GET/HEAD/OPTIONS 有效**

理由：浏览器 SPA 没法安全持有 API Key，``<img src>`` 也发不了请求头，
所以读接口和截图必须能用 Cookie；但 Cookie 一旦能用于写接口就等于开了 CSRF。
所有会改状态的路由都是 POST/PUT/PATCH/DELETE（已逐条核对）。

其余：/health 永远公开（部署探针）；API_KEY 为空 = 整体不校验（本机开发）。
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

    @app.put("/v1/brands/1/aliases")
    def put_aliases():
        return {"ok": True}

    @app.patch("/v1/brands/1")
    def patch_brand():
        return {"ok": True}

    @app.delete("/v1/brands/1")
    def delete_brand():
        return {"ok": True}

    @app.get("/v1/counts")
    def counts():
        return {"n_valid": 35}

    @app.get("/v1/media/screenshots/{name}")
    def media(name: str):
        return {"file": name}

    @app.get("/qa")
    def qa_home():
        return {"page": "qa"}

    # 真实的登录路由（只挑不碰数据库的三个）
    app.add_api_route("/qa/login", qa_router.qa_login_form, methods=["GET"])
    app.add_api_route("/qa/login", qa_router.qa_login, methods=["POST"])
    return app


#: TestClient 默认 base_url 是 **http**://testserver，而生产
#: `API_COOKIE_SECURE=true` 下发的是 Secure Cookie —— Secure Cookie 不在 http 上
#: 回传，于是 `test_login_sets_cookie_and_grants_qa` 在 VPS 上必挂 401，
#: 本机（没设那个 env）却过。
#:
#: 改成 https 而不是把 `API_COOKIE_SECURE` 钉成 false：钉成 false 只是让用例
#: 绕开生产配置，https 才是**生产的形状**，而且两种配置下都成立。
BASE_URL = "https://testserver"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEY", KEY)
    get_settings.cache_clear()
    yield TestClient(build_app(), base_url=BASE_URL)
    get_settings.cache_clear()


@pytest.fixture
def open_client(monkeypatch):
    monkeypatch.setenv("API_KEY", "")
    get_settings.cache_clear()
    yield TestClient(build_app(), base_url=BASE_URL)
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
    client.cookies.set(QA_COOKIE_NAME, KEY, path="/")
    assert client.get("/qa").status_code == 200


@pytest.mark.parametrize("path", ["/v1/counts", "/v1/media/screenshots/a.png"])
def test_cookie_works_for_get_on_v1(client, path):
    """F0a：读接口与截图必须能用 Cookie —— <img src> 发不了请求头。"""
    client.cookies.set(QA_COOKIE_NAME, KEY, path="/")
    assert client.get(path).status_code == 200


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/v1/brands"),
        ("put", "/v1/brands/1/aliases"),
        ("patch", "/v1/brands/1"),
        ("delete", "/v1/brands/1"),
    ],
)
def test_cookie_never_works_for_write_methods(client, method, path):
    """CSRF 红线：Cookie 对任何写方法都无效，逐个方法验。"""
    client.cookies.set(QA_COOKIE_NAME, KEY, path="/")
    assert getattr(client, method)(path).status_code == 401


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/v1/brands"),
        ("put", "/v1/brands/1/aliases"),
        ("patch", "/v1/brands/1"),
        ("delete", "/v1/brands/1"),
    ],
)
def test_header_still_works_for_write_methods(client, method, path):
    client.cookies.set(QA_COOKIE_NAME, "wrong-cookie", path="/")
    r = getattr(client, method)(path, headers={"X-API-Key": KEY})
    assert r.status_code == 200


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
    # path=/ 而非 /qa：F0b 起前端挂在 /，GET /v1/* 与截图也要带上它。
    # 放宽作用域不引入 CSRF —— Cookie 只在安全方法上生效。
    assert "Path=/" in cookie and "Path=/qa" not in cookie
    assert client.get("/qa").status_code == 200
    assert client.get("/v1/counts").status_code == 200


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
