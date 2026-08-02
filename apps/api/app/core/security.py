"""API Key 鉴权（P0：本服务在公网 8200 端口上暴露）.

分界线不是**路径**，而是 **HTTP 方法**：

===============  ==========================================================
请求头认证        任何方法都接受（``X-API-Key`` 或 ``Authorization: Bearer``）
Cookie 认证       **只对安全方法**（GET/HEAD/OPTIONS）有效
===============  ==========================================================

为什么这样切（F0a，2026-08-02）：

浏览器里的 SPA **没法安全持有 API Key**（打包进去 F12 就能拿到），而
``<img src>`` 又**发不了自定义请求头** —— 证据截图必须靠 Cookie 才能显示。
所以 Cookie 必须能用于读接口。

但 Cookie 一旦能用于写接口，第三方站点就能诱导浏览器发起 CSRF 写操作。
按方法切正好挡住这一点：

- 所有会改状态的路由都是 POST/PUT/PATCH/DELETE（已逐条核对），
  它们只认请求头，跨站构造不出来
- GET 用 Cookie 是安全的：跨站发得出请求，但没有 CORS 头就读不到响应体，
  而 GET 本身不改状态

``API_KEY`` 为空 = 不启用鉴权（本机开发用），启动时会打 WARNING。
"""
from __future__ import annotations

import logging
import secrets
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from app.core.config import get_settings

logger = logging.getLogger("geo.security")

QA_COOKIE_NAME = "geo_qa_key"

# 不需要鉴权的路径：部署脚本 / 容器健康检查要用
PUBLIC_PATHS = frozenset({"/health", "/qa/login", "/favicon.ico"})

# Cookie 只对这些方法有效 —— 它们不改状态，跨站也读不到响应
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# 未认证的 HTML 请求跳到这里
LOGIN_PATH = "/qa/login"


def api_key_configured() -> bool:
    return bool(get_settings().api_key)


def verify_key(candidate: Optional[str]) -> bool:
    """常数时间比较，避免按字节比较被计时侧信道试探。"""
    expected = get_settings().api_key
    if not expected:
        return True
    if not candidate:
        return False
    return secrets.compare_digest(candidate, expected)


def _key_from_headers(request: Request) -> Optional[str]:
    header = request.headers.get("x-api-key")
    if header:
        return header.strip()
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def _wants_html(request: Request) -> bool:
    return "text/html" in (request.headers.get("accept") or "")


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not api_key_configured():
            return await call_next(request)

        path = request.url.path
        if path in PUBLIC_PATHS:
            return await call_next(request)

        if verify_key(_key_from_headers(request)):
            return await call_next(request)

        # Cookie 只对安全方法有效 —— 写接口拿不到 Cookie 认证，CSRF 无从下手
        if request.method in SAFE_METHODS:
            if verify_key(request.cookies.get(QA_COOKIE_NAME)):
                return await call_next(request)
            if _wants_html(request) and path != LOGIN_PATH:
                return RedirectResponse(url=LOGIN_PATH, status_code=302)

        return JSONResponse(
            status_code=401,
            content={"detail": "missing or invalid API key (X-API-Key)"},
        )


def set_qa_cookie(response: Response, key: str, *, secure: bool) -> None:
    # path="/"：前端（F0b 起挂在 /）与 GET /v1/*、媒体路由都要带上它。
    # 作用域放宽不引入 CSRF —— 中间件只在安全方法上认 Cookie。
    response.set_cookie(
        QA_COOKIE_NAME,
        key,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=7 * 24 * 3600,
        path="/",
    )


def clear_qa_cookie(response: Response) -> None:
    response.delete_cookie(QA_COOKIE_NAME, path="/")


def warn_if_open() -> None:
    if not api_key_configured():
        logger.warning(
            "API_KEY 未设置 —— 所有接口无鉴权。若本服务对公网开放（compose 默认 8200:8200），"
            "任何人都可以删除品牌、灌入 L0、触发抓取。请在 deploy/.env 设置 API_KEY。"
        )
