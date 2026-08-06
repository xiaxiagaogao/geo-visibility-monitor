"""``/v1/users/*`` —— 只有超管能用。"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.api.deps import get_db, require_superadmin
from app.core.auth import ROLE_CLIENT, ROLES, hash_password, revoke_all_sessions
from app.core.security import Principal
from app.models import User

router = APIRouter(prefix="/v1/users", tags=["users"])

MIN_PASSWORD_LEN = 12


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    workspace_id: Optional[int] = None
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UserListOut(BaseModel):
    items: List[UserOut]
    total: int


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=MIN_PASSWORD_LEN)
    role: str
    workspace_id: Optional[int] = None


class UserUpdate(BaseModel):
    role: Optional[str] = None
    workspace_id: Optional[int] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=MIN_PASSWORD_LEN)


def _validate_role_workspace(role: str, workspace_id: Optional[int]) -> Optional[int]:
    if role not in ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"role must be one of {list(ROLES)}",
        )
    if role == ROLE_CLIENT:
        if workspace_id is None:
            # 没有 workspace 的客户什么都看不到 —— 与其建个废账号，不如当场报错
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="client role requires workspace_id",
            )
        return workspace_id
    # 超管/运营看全部，带 workspace 只会误导后来读库的人
    return None


@router.get("", response_model=UserListOut)
def list_users(
    db: DbSession = Depends(get_db),
    _: Principal = Depends(require_superadmin),
):
    rows = list(db.scalars(select(User).order_by(User.id)).all())
    return UserListOut(items=[UserOut.model_validate(u) for u in rows], total=len(rows))


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    db: DbSession = Depends(get_db),
    _: Principal = Depends(require_superadmin),
):
    email = body.email.strip().lower()
    if db.scalars(select(User).where(User.email == email)).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already exists")
    ws = _validate_role_workspace(body.role, body.workspace_id)
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        role=body.role,
        workspace_id=ws,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdate,
    db: DbSession = Depends(get_db),
    admin: Principal = Depends(require_superadmin),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    role = body.role or user.role
    ws = body.workspace_id if body.workspace_id is not None else user.workspace_id
    if body.role is not None or body.workspace_id is not None:
        user.workspace_id = _validate_role_workspace(role, ws)
        user.role = role

    # 改密与停用**必须**吊销该用户全部会话，否则旧会话继续有效，等于没改
    must_revoke = False
    if body.password is not None:
        user.password_hash = hash_password(body.password)
        must_revoke = True
    if body.is_active is not None and body.is_active != user.is_active:
        user.is_active = body.is_active
        if not body.is_active:
            must_revoke = True

    db.commit()
    if must_revoke:
        revoke_all_sessions(db, user.id)
    db.refresh(user)
    return UserOut.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: DbSession = Depends(get_db),
    admin: Principal = Depends(require_superadmin),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    # 不许删掉自己 —— 超管删光后就没人能管用户了，只能进库改
    if admin.user_id is not None and admin.user_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cannot delete yourself",
        )
    db.delete(user)  # sessions 靠 ON DELETE CASCADE 一起走
    db.commit()
