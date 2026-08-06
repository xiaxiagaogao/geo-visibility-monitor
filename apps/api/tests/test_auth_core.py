"""D2 凭证层：密码哈希与会话签发/校验（不依赖数据库的部分）。

会话相关用例需要真库，标了 pg 依赖的会自动 skip（本机无 Postgres）。
"""
from __future__ import annotations

import pytest

from app.core.auth import (
    ROLES,
    SESSION_TTL,
    hash_password,
    hash_token,
    new_csrf_token,
    verify_password,
)


def test_password_roundtrip():
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong password entirely", h)


def test_hash_is_salted_so_same_password_differs():
    """同一密码两次哈希必须不同 —— 否则等于泄露「这两个账号密码一样」。"""
    a = hash_password("same-password-12345")
    b = hash_password("same-password-12345")
    assert a != b
    assert verify_password("same-password-12345", a)
    assert verify_password("same-password-12345", b)


def test_hash_is_argon2_not_plaintext():
    h = hash_password("my-secret-pw-123")
    assert h.startswith("$argon2"), "必须是 argon2 哈希"
    assert "my-secret-pw-123" not in h


@pytest.mark.parametrize("bad", ["", "not-a-hash", "$argon2id$broken", None])
def test_verify_never_raises_on_garbage(bad):
    """哈希损坏也只能返回 False。

    抛异常会让「密码错」和「数据坏了」在响应上可区分 —— 那是账号枚举的入口。
    """
    assert verify_password("whatever", bad) is False


def test_token_hash_is_sha256_hex():
    h = hash_token("some-session-token")
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)
    # 确定性：同 token 同哈希，否则查不到会话
    assert h == hash_token("some-session-token")
    assert h != hash_token("some-session-token2")


def test_csrf_tokens_are_unique_and_long():
    a, b = new_csrf_token(), new_csrf_token()
    assert a != b
    assert len(a) >= 32


def test_roles_are_exactly_three():
    assert set(ROLES) == {"superadmin", "operator", "client"}


def test_session_ttl_is_seven_days():
    """固定 7 天、不滑动续期 —— 设计稿 §11 B 的拍板。"""
    assert SESSION_TTL.days == 7
