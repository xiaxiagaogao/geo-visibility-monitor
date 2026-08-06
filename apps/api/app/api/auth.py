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


def _set_auth_cookies(response: Response, token: str, csrf: str) -> None:
    s = get_settings()
    samesite = (s.api_cookie_samesite or "lax").lower()
    secure = s.api_cookie_secure or samesite == "none"
    max_age = int(SESSION_TTL.total_seconds())

    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,  # JS 读不到 → XSS 偷不走会话
        samesite=samesite,
        secure=secure,
        max_age=max_age,
        path="/",
    )
    # CSRF token 必须 **httponly=False** —— 前端要读它并回填到请求头，
    # 这正是双提交的原理：跨站攻击者读不到本站 Cookie，就造不出匹配的头。
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf,
        httponly=False,
        samesite=samesite,
        secure=secure,
        max_age=max_age,
        path="/",
    )


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
    _set_auth_cookies(response, token, new_csrf_token())
    return MeOut(
        user_id=user.id,
        email=user.email,
        role=user.role,
        workspace_id=user.workspace_id,
        kind="user",
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: DbSession = Depends(get_db)):
    revoke_session(db, request.cookies.get(SESSION_COOKIE_NAME))
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")


@router.get("/me", response_model=MeOut)
def me(
    principal: Principal = Depends(current_principal),
    db: DbSession = Depends(get_db),
):
    """前端据此渲染菜单与按钮 —— 但**权限判断始终在服务端**，这里只是给 UI 用。"""
    if not principal.is_authenticated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not logged in")

    email = None
    if principal.user_id is not None:
        user = db.get(User, principal.user_id)
        email = user.email if user else None

    return MeOut(
        user_id=principal.user_id,
        email=email,
        role=principal.effective_role or "unknown",
        workspace_id=principal.workspace_id,
        kind=principal.kind,
    )
