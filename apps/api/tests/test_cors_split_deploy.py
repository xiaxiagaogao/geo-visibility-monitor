"""前后端分离部署：CORS 与跨站 Cookie（不依赖数据库）。

D1 把前端从「geo-api 托管的静态目录」改成**独立部署的产品**，随之要解决三件事：

1. 跨站请求要带 Cookie → ``SameSite=None; Secure``（浏览器强制成对）
2. 浏览器要放行跨源读取 → CORS，且带凭证时**不允许** ``*``
3. **放宽 SameSite 不能把 CSRF 放进来** —— 这是本文件最要紧的一组用例

第 3 点的防线仍然是「Cookie 只对 GET/HEAD/OPTIONS 有效」。SameSite=None 之后
跨站**发得出**请求，但发出来的写操作依然认不了 Cookie，所以构造不出被认证的写。
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from starlette.responses import Response

from app.core.config import get_settings
from app.core.security import QA_COOKIE_NAME, ApiKeyMiddleware, set_qa_cookie

KEY = "split-deploy-key"
FRONTEND = "https://geo.example.com"


def build_app(*, origins: list[str]) -> FastAPI:
    """复刻 main.py 的中间件顺序：CORS 后加 → 在外层 → 先处理预检。"""
    app = FastAPI()

    @app.get("/v1/counts")
    def counts():
        return {"ok": True}

    @app.post("/v1/brands")
    def create_brand():
        return {"ok": True}

    @app.get("/v1/media/screenshots/{name}")
    def shot(name: str):
        return Response(content=b"png", media_type="image/png")

    app.add_middleware(ApiKeyMiddleware)
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    return app


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("API_KEY", KEY)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_preflight_is_answered_before_auth():
    """预检 OPTIONS 不带凭证。中间件顺序反了的话它会撞上 401 而没有 CORS 头，
    现象是「浏览器全挂但 curl 正常」—— 最费时间的一类故障。"""
    c = TestClient(build_app(origins=[FRONTEND]))
    r = c.options(
        "/v1/counts",
        headers={"Origin": FRONTEND, "Access-Control-Request-Method": "GET"},
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == FRONTEND
    assert r.headers["access-control-allow-credentials"] == "true"


def test_cross_origin_get_with_cookie_is_allowed_and_echoes_origin():
    c = TestClient(build_app(origins=[FRONTEND]))
    c.cookies.set(QA_COOKIE_NAME, KEY)
    r = c.get("/v1/counts", headers={"Origin": FRONTEND})
    assert r.status_code == 200
    # 带凭证时必须回显具体 Origin，不能是 *
    assert r.headers["access-control-allow-origin"] == FRONTEND


def test_unlisted_origin_gets_no_cors_header():
    c = TestClient(build_app(origins=[FRONTEND]))
    c.cookies.set(QA_COOKIE_NAME, KEY)
    r = c.get("/v1/counts", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_screenshot_readable_cross_origin_with_cookie():
    """证据截图靠 <img src> 加载，带不了请求头 —— 分离部署后只能靠跨站 Cookie。"""
    c = TestClient(build_app(origins=[FRONTEND]))
    c.cookies.set(QA_COOKIE_NAME, KEY)
    r = c.get("/v1/media/screenshots/a.png", headers={"Origin": FRONTEND})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


def test_csrf_line_holds_after_samesite_none():
    """**最要紧的一条**：放宽 SameSite 之后，跨站写操作依然认不了 Cookie。"""
    c = TestClient(build_app(origins=[FRONTEND]))
    c.cookies.set(QA_COOKIE_NAME, KEY)
    r = c.post("/v1/brands", headers={"Origin": FRONTEND}, json={})
    assert r.status_code == 401, "Cookie 绝不能认证写操作，否则 CORS 白名单成了唯一防线"


def test_write_still_works_with_header():
    c = TestClient(build_app(origins=[FRONTEND]))
    r = c.post("/v1/brands", headers={"Origin": FRONTEND, "X-API-Key": KEY}, json={})
    assert r.status_code == 200


def test_no_cors_headers_when_disabled():
    """同源部署（不配 origins）不应凭空长出 CORS 头。"""
    c = TestClient(build_app(origins=[]))
    c.cookies.set(QA_COOKIE_NAME, KEY)
    r = c.get("/v1/counts", headers={"Origin": FRONTEND})
    assert r.status_code == 200
    assert "access-control-allow-origin" not in r.headers


# ---------- Cookie 属性 ----------


def _cookie_header(**kw) -> str:
    resp = Response()
    set_qa_cookie(resp, KEY, **kw)
    return resp.headers["set-cookie"].lower()


def test_samesite_none_forces_secure():
    """浏览器规定 SameSite=None 必须 Secure，否则静默丢弃 —— 代码里强制成对，
    免得部署成「登录了但一直 401」。"""
    h = _cookie_header(secure=False, samesite="none")
    assert "samesite=none" in h
    assert "secure" in h


def test_lax_default_unchanged_for_same_origin():
    h = _cookie_header(secure=False, samesite="lax")
    assert "samesite=lax" in h
    assert "secure" not in h


def test_cookie_is_httponly_and_root_path():
    h = _cookie_header(secure=True, samesite="none")
    assert "httponly" in h
    assert "path=/" in h


def test_bogus_samesite_falls_back_to_lax():
    assert "samesite=lax" in _cookie_header(secure=False, samesite="whatever")


# ---------- CDN 缓存 ----------


def test_screenshot_is_not_cacheable_by_shared_caches(tmp_path, monkeypatch):
    """证据截图必须带 private,no-store。

    URL 以 .png 结尾，CDN（本项目走 Cloudflare）会按扩展名把它当静态资源
    缓存到边缘 —— 之后任何拿到 URL 的人都能绕过鉴权取到图。
    """
    from app.api import qa as qa_router

    shot = tmp_path / "evidence.png"
    shot.write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setenv("SCREENSHOT_DIR", str(tmp_path))
    monkeypatch.delenv("API_KEY", raising=False)  # 本用例只关心缓存头
    get_settings.cache_clear()

    app = FastAPI()
    app.include_router(qa_router.router)
    # 这个 app 没挂中间件，身份默认是匿名，而归属校验对匿名是 fail-closed（401）。
    # 本用例只关心缓存头，所以直接注入一个机器身份。
    from app.api.deps import current_principal
    from app.core.security import MACHINE

    app.dependency_overrides[current_principal] = lambda: MACHINE
    r = TestClient(app).get("/v1/media/screenshots/evidence.png")

    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    cc = r.headers.get("cache-control", "").lower()
    assert "no-store" in cc and "private" in cc, (
        f"截图响应缺少缓存控制（实际 Cache-Control={cc!r}），会被 CDN 缓存到边缘"
    )
