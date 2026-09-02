"""``/v1/auth/*`` —— 登录、登出、我是谁。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.api.deps import current_principal, get_db
from app.core.auth import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    SESSION_TTL,
    issue_session,
    new_csrf_token,
    revoke_session,
    verify_password,
)
from app.core.config import get_settings
from app.core.security import Principal
from app.models import User

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class MeOut(BaseModel):
    user_id: Optional[int] = None
    email: Optional[str] = None
    role: str
    workspace_id: Optional[int] = None
    #: machine = 共享密钥 / QA 后门（等同超管但没有用户身份）
    kind: str
    #: 双提交用的 CSRF token。**必须放响应体，不能只放 Cookie** ——
    #: 分离部署下前端在 geo.example.com，而 Cookie 是 geo-api.example.com 的 host-only，
    #: document.cookie 读不到。给 Cookie 加 Domain=.example.com 也不行：
    #: 同机还有 fund./option. 两个不相干项目，会把会话 Cookie 发给它们。
    #: 安全性与双提交等价 —— 跨站攻击者读不到这个响应体（CORS 只允许前端 Origin）。
    #: machine 身份（X-API-Key）不走 Cookie，此字段为 None。
    csrf_token: Optional[str] = None


def _cookie_opts() -> dict:
    s = get_settings()
    samesite = (s.api_cookie_samesite or "lax").lower()
    return {
        "samesite": samesite,
        "secure": s.api_cookie_secure or samesite == "none",
        "max_age": int(SESSION_TTL.total_seconds()),
        "path": "/",
    }


def _set_csrf_cookie(response: Response, csrf: str) -> None:
    """CSRF token 的服务端那一半。

    `httponly=False` 是**同源部署**下双提交的原理：前端 JS 读它回填请求头，
    跨站攻击者读不到本站 Cookie，就造不出匹配的头。

    但**分离部署下前端读不到它** —— 它是 `geo-api.example.com` 的 host-only Cookie，
    而前端在 `geo.example.com`。所以同一个值还要经 `MeOut.csrf_token` 交给前端，
    见那里的注释。这里保留 `httponly=False` 只是为了同源场景（`/qa`、开发期代理）
    仍然能用老办法读。
    """
    response.set_cookie(CSRF_COOKIE_NAME, csrf, httponly=False, **_cookie_opts())


def _set_auth_cookies(response: Response, token: str, csrf: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,  # JS 读不到 → XSS 偷不走会话
        **_cookie_opts(),
    )
    _set_csrf_cookie(response, csrf)


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, response: Response, db: DbSession = Depends(get_db)):
    email = body.email.strip().lower()
    user = db.scalars(select(User).where(User.email == email)).first()

    # 用户不存在 / 密码错 / 账号停用 —— 对外都是同一条消息、同一个状态码。
    # 区分开就等于提供账号枚举接口（「这个邮箱存在但密码错」）。
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="email or password is incorrect",
        )

    token = issue_session(db, user)
    # 先生成再分别用于 Cookie 与响应体 —— 各自生成一个的话，
    # Cookie 里是 A、前端拿到 B，写操作会被判成不匹配而 403，
    # 且只在打开 CSRF 开关之后才显形。
    csrf = new_csrf_token()
    _set_auth_cookies(response, token, csrf)
    return MeOut(
        user_id=user.id,
        email=user.email,
        role=user.role,
        workspace_id=user.workspace_id,
        kind="user",
        csrf_token=csrf,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: DbSession = Depends(get_db)):
    revoke_session(db, request.cookies.get(SESSION_COOKIE_NAME))
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")


@router.get("/me", response_model=MeOut)
def me(
    request: Request,
    response: Response,
    principal: Principal = Depends(current_principal),
    db: DbSession = Depends(get_db),
):
    """前端据此渲染菜单与按钮 —— 但**权限判断始终在服务端**，这里只是给 UI 用。

    顺带把 CSRF token 交还给前端：刷新页面后内存里的值就没了，
    前端靠这个端点重新拿到，不必让用户重新登录。
    """
    if not principal.is_authenticated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not logged in")

    email = None
    if principal.user_id is not None:
        user = db.get(User, principal.user_id)
        email = user.email if user else None

    # 回显请求里带来的那个值，**不是新发一个** ——
    # 每次调 /me 都换新的话，另一个标签页里正在用的 token 会被作废。
    csrf = request.cookies.get(CSRF_COOKIE_NAME)
    if csrf is None and principal.kind == "user":
        # 会话还在、csrf Cookie 没了（两者 max_age 相同，正常不会分家，
        # 但用户手工清 Cookie 或换浏览器策略都可能造成）。
        # 不补发的话，用户会卡在「登录着但所有写操作 403」且界面看不出原因。
        csrf = new_csrf_token()
        _set_csrf_cookie(response, csrf)

    return MeOut(
        user_id=principal.user_id,
        email=email,
        role=principal.effective_role or "unknown",
        workspace_id=principal.workspace_id,
        kind=principal.kind,
        csrf_token=csrf,
    )
