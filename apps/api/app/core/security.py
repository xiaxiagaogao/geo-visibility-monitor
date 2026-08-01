"""API Key 鉴权（P0：本服务在公网 8200 端口上暴露）.

两条通道，故意分开：

- ``/v1/*``、``/docs`` 等：只认 **请求头**（``X-API-Key`` 或 ``Authorization: Bearer``）。
  写接口不接受 Cookie，浏览器带着 Cookie 也无法被第三方站点诱导发起 CSRF 写操作。
- ``/qa/*``：额外接受 HttpOnly Cookie（浏览器没法自己加请求头）。
  QA 页面全是 GET，只读，用 Cookie 不引入 CSRF 面。

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

# 只有这些前缀允许用 Cookie 认证（只读页面）
COOKIE_ALLOWED_PREFIXES = ("/qa",)


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

        # 只读 QA 页面可以用 Cookie；/v1 写接口一律不认 Cookie
        if path.startswith(COOKIE_ALLOWED_PREFIXES):
            if verify_key(request.cookies.get(QA_COOKIE_NAME)):
                return await call_next(request)
            if _wants_html(request):
                return RedirectResponse(url="/qa/login", status_code=302)

        return JSONResponse(
            status_code=401,
            content={"detail": "missing or invalid API key (X-API-Key)"},
        )


def set_qa_cookie(response: Response, key: str, *, secure: bool) -> None:
    response.set_cookie(
        QA_COOKIE_NAME,
        key,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=7 * 24 * 3600,
        path="/qa",
    )


def clear_qa_cookie(response: Response) -> None:
    response.delete_cookie(QA_COOKIE_NAME, path="/qa")


def warn_if_open() -> None:
    if not api_key_configured():
        logger.warning(
            "API_KEY 未设置 —— 所有接口无鉴权。若本服务对公网开放（compose 默认 8200:8200），"
            "任何人都可以删除品牌、灌入 L0、触发抓取。请在 deploy/.env 设置 API_KEY。"
        )
