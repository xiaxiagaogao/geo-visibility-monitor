"""D2：密码哈希、会话签发与校验、角色定义。

这一层**只做纯粹的凭证操作**，不碰 HTTP、不判权限：

- 密码：argon2（慢哈希，抗爆破）
- 会话 token：32 字节随机 → 明文只发给浏览器一次，库里存 SHA-256

**为什么两种哈希不一样**：密码是低熵、人选的，必须用慢哈希拖住离线爆破；
会话 token 是 32 字节高熵随机值，本就爆破不动，而每个请求都要查一次 ——
在这里用慢哈希只会把它变成性能负担，没有安全收益。
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from app.models import Session as SessionRow
from app.models import User

# ---------- 角色 ----------

ROLE_SUPERADMIN = "superadmin"
ROLE_OPERATOR = "operator"
ROLE_CLIENT = "client"
ROLES = (ROLE_SUPERADMIN, ROLE_OPERATOR, ROLE_CLIENT)

#: 能改配置、建品牌/提问词、发起抓取的角色。客户是纯只读。
WRITE_ROLES = frozenset({ROLE_SUPERADMIN, ROLE_OPERATOR})
#: 能看全部数据（不受 workspace 限制）的角色
GLOBAL_READ_ROLES = frozenset({ROLE_SUPERADMIN, ROLE_OPERATOR})

SESSION_COOKIE_NAME = "geo_session"
CSRF_COOKIE_NAME = "geo_csrf"
CSRF_HEADER_NAME = "x-csrf-token"

SESSION_TTL = timedelta(days=7)  # 固定 7 天，不滑动续期

#: 密码最短长度。
#:
#: **放这里是因为原先有两份**：``api/users.py`` 和 ``scripts/create_user.py``
#: 各写了一个 12，谁也不知道对方存在。两份约束迟早只改一边 —— 那时
#: API 收得下的密码，脚本会拒绝（或者反过来），而两边都不会报错，
#: 只是行为对不上。这类常量必须只有一个定义处。
MIN_PASSWORD_LEN = 8

_hasher = PasswordHasher()


# ---------- 密码 ----------


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """常数时间由 argon2 保证；任何异常一律当作「不匹配」。

    不区分「密码错」与「哈希损坏」——对外只有一个结果，避免用错误信息区分账号状态。
    """
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHashError, Exception):  # noqa: BLE001
        return False


# ---------- 会话 ----------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def issue_session(db: DbSession, user: User) -> str:
    """新建会话，返回**明文 token**（只在这一刻存在，之后库里只有哈希）。"""
    token = secrets.token_urlsafe(32)
    db.add(
        SessionRow(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=_now() + SESSION_TTL,
        )
    )
    user.last_login_at = _now()
    db.commit()
    return token


def resolve_session(db: DbSession, token: Optional[str]) -> Optional[User]:
    """token → User。过期、被删、用户停用，一律返回 None。

    过期的行顺手删掉：会话表没有别的清理入口，靠每次命中时收拾就够了。
    """
    if not token:
        return None
    row = db.scalars(
        select(SessionRow).where(SessionRow.token_hash == hash_token(token))
    ).first()
    if row is None:
        return None

    expires = row.expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires is None or expires <= _now():
        db.delete(row)
        db.commit()
        return None

    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    return user


def revoke_session(db: DbSession, token: Optional[str]) -> None:
    if not token:
        return
    db.execute(delete(SessionRow).where(SessionRow.token_hash == hash_token(token)))
    db.commit()


def revoke_all_sessions(db: DbSession, user_id: int) -> int:
    """改密码或停用账号时调用 —— 否则旧会话继续有效，等于没停。"""
    result = db.execute(delete(SessionRow).where(SessionRow.user_id == user_id))
    db.commit()
    return result.rowcount or 0
