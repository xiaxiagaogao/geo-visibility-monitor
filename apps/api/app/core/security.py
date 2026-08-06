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
from dataclasses import dataclass
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from app.core.config import get_settings

logger = logging.getLogger("geo.security")

QA_COOKIE_NAME = "geo_qa_key"
#: D2 用户会话 Cookie（与 core/auth.py 保持一致，此处重复定义以免循环导入）
SESSION_COOKIE_NAME = "geo_session"

# 不需要鉴权的路径：部署脚本 / 容器健康检查 / 登录本身
PUBLIC_PATHS = frozenset(
    {"/health", "/qa/login", "/favicon.ico", "/v1/auth/login"}
)

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


@dataclass(frozen=True)
class Principal:
    """「这个请求是谁」。由中间件解析，放在 ``request.state.principal``。

    三种来源见 D2 设计稿 §1。``machine`` 是共享密钥与 ``/qa`` 后门，
    **等同超管但没有用户身份**（拿不到 user_id，也不受 workspace 限制）。
    """

    kind: str  # machine | user | anonymous
    user_id: Optional[int] = None
    role: Optional[str] = None
    workspace_id: Optional[int] = None

    @property
    def is_authenticated(self) -> bool:
        return self.kind != "anonymous"

    @property
    def effective_role(self) -> Optional[str]:
        """machine 折算成超管，这样权限判断只需要看一个字段。"""
        if self.kind == "machine":
            return "superadmin"
        return self.role

    @property
    def can_write(self) -> bool:
        from app.core.auth import WRITE_ROLES

        return self.effective_role in WRITE_ROLES

    @property
    def sees_all_brands(self) -> bool:
        """False = 只能看自己 workspace 的品牌（client）。"""
        from app.core.auth import GLOBAL_READ_ROLES

        return self.effective_role in GLOBAL_READ_ROLES


ANONYMOUS = Principal(kind="anonymous")
MACHINE = Principal(kind="machine")


def _resolve_user_principal(token: Optional[str]) -> Optional[Principal]:
    """会话 Cookie → Principal。要查库，所以单独拆出来便于测试替换。"""
    if not token:
        return None
    # 延迟导入：security 是底层模块，不该在导入期就拉起 ORM 与连接池
    from app.core.auth import resolve_session
    from app.core.db import SessionLocal

    db = SessionLocal()
    try:
        user = resolve_session(db, token)
        if user is None:
            return None
        return Principal(
            kind="user",
            user_id=user.id,
            role=user.role,
            workspace_id=user.workspace_id,
        )
    finally:
        db.close()


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """认证（不是授权）。

    **只认「你是谁」，不判「你能干什么」** —— 后者在路由依赖里做，
    因为中间件看不到路径参数与查询参数，做不了归属校验（D2 设计稿 §7）。

    放在中间件而不是依赖里，是为了 **fail-closed**：默认拒绝，
    只有 ``PUBLIC_PATHS`` 例外。若改成逐路由挂依赖，漏挂一个就是一个开放接口。
    """

    async def dispatch(self, request: Request, call_next):
        request.state.principal = ANONYMOUS

        if not api_key_configured():
            # 本机开发：不设 API_KEY 即整体不校验（启动时已 WARNING）
            request.state.principal = MACHINE
            return await call_next(request)

        path = request.url.path
        if path in PUBLIC_PATHS:
            return await call_next(request)

        # ① 共享密钥（机器）——任何方法
        if verify_key(_key_from_headers(request)):
            request.state.principal = MACHINE
            return await call_next(request)

        # ② 用户会话 —— 任何方法。写操作的 CSRF 防护由 D2-4 的双提交 token 负责
        session_principal = _resolve_user_principal(
            request.cookies.get(SESSION_COOKIE_NAME)
        )
        if session_principal is not None:
            request.state.principal = session_principal
            return await call_next(request)

        # ③ /qa 后门 Cookie —— 只对安全方法，写接口认不了它，CSRF 无从下手
        if request.method in SAFE_METHODS:
            if verify_key(request.cookies.get(QA_COOKIE_NAME)):
                request.state.principal = MACHINE
                return await call_next(request)
            if _wants_html(request) and path != LOGIN_PATH:
                return RedirectResponse(url=LOGIN_PATH, status_code=302)

        return JSONResponse(
            status_code=401,
            # 提示要列全通道：调用方看到「缺 X-API-Key」却在用会话登录时会一头雾水
            content={
                "detail": "missing or invalid credentials "
                "(X-API-Key header, or log in via POST /v1/auth/login)"
            },
        )


def set_qa_cookie(
    response: Response,
    key: str,
    *,
    secure: bool,
    samesite: str = "lax",
) -> None:
    """下发读取用 Cookie。

    ``samesite``：同源部署用 ``lax``；**前后端分离部署必须用 ``none``**，
    否则跨站请求（含证据截图的 ``<img src>``）根本不会带上它。

    ``none`` 会放宽到「任何站点发起的请求都带 Cookie」，但**不会引入 CSRF** ——
    中间件只在 GET/HEAD/OPTIONS 上认 Cookie，跨站构造不出被认证的写操作
    （``test_cookie_never_works_for_write_methods`` 逐方法守着）。

    浏览器硬性要求 ``SameSite=None`` 必须同时 ``Secure``，所以这里强制成对，
    否则 Cookie 会被静默丢弃 —— 那种故障现象是「登录了但一直 401」，极难排查。
    """
    samesite = (samesite or "lax").lower()
    if samesite not in ("lax", "strict", "none"):
        samesite = "lax"
    if samesite == "none" and not secure:
        logger.warning(
            "api_cookie_samesite=none 需要 api_cookie_secure=true（浏览器强制），"
            "已自动置 secure=true；若当前不是 HTTPS，登录会表现为「一直 401」。"
        )
        secure = True
    # path="/"：GET /v1/* 与媒体路由都要带上它。
    # 作用域放宽不引入 CSRF —— 中间件只在安全方法上认 Cookie。
    response.set_cookie(
        QA_COOKIE_NAME,
        key,
        httponly=True,
        samesite=samesite,
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
    _warn_split_deploy_misconfig()


def _warn_split_deploy_misconfig() -> None:
    """分离部署的三个配置必须成套，缺一个就是「登录了但一直 401」。

    这类故障没有任何报错，浏览器只是静默不带 Cookie，排查成本极高，
    所以在启动时就把话说清楚。
    """
    s = get_settings()
    origins = s.cors_origins
    samesite = (s.api_cookie_samesite or "lax").lower()

    if origins and samesite != "none":
        logger.warning(
            "已配置 CORS_ALLOW_ORIGINS=%s（分离部署），但 API_COOKIE_SAMESITE=%s。"
            "跨站请求不会带上 Cookie —— 读接口与证据截图都会 401。应设为 none。",
            origins,
            samesite,
        )
    if samesite == "none" and not s.api_cookie_secure:
        logger.warning(
            "API_COOKIE_SAMESITE=none 但 API_COOKIE_SECURE=false —— "
            "浏览器会直接丢弃该 Cookie。必须走 HTTPS 并置 API_COOKIE_SECURE=true。"
        )
    if not origins and samesite == "none":
        logger.warning(
            "API_COOKIE_SAMESITE=none 却没有配置 CORS_ALLOW_ORIGINS —— "
            "同源部署无需放宽 SameSite，这样只是白白扩大 Cookie 的发送面。"
        )
