"""D2-2：三条身份通道与 Principal 的权限语义（不依赖数据库）。

会话解析被 monkeypatch 掉 —— 这里验的是**中间件挑通道的顺序与结论**，
真库上的登录闭环见 test_auth_flow.py。
"""
from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.deps import current_principal, require_superadmin, require_write
from app.core.config import get_settings
from app.core.security import (
    QA_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    ApiKeyMiddleware,
    Principal,
)

KEY = "principal-test-key"


def build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/v1/whoami")
    def whoami(p: Principal = Depends(current_principal)):
        return {"kind": p.kind, "role": p.effective_role, "workspace_id": p.workspace_id}

    @app.post("/v1/write-thing")
    def write_thing(p: Principal = Depends(require_write)):
        return {"ok": True}

    @app.post("/v1/admin-thing")
    def admin_thing(p: Principal = Depends(require_superadmin)):
        return {"ok": True}

    app.add_middleware(ApiKeyMiddleware)
    return app


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("API_KEY", KEY)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def as_user(monkeypatch):
    """把会话解析替换掉，直接返回指定角色的用户。"""

    def _install(role: str, workspace_id=None, user_id=7):
        def fake(token):
            if token == "valid-session":
                return Principal(
                    kind="user", user_id=user_id, role=role, workspace_id=workspace_id
                )
            return None

        monkeypatch.setattr("app.core.security._resolve_user_principal", fake)

    return _install


# ---------- 通道 ----------


def test_shared_key_is_machine_and_counts_as_superadmin():
    c = TestClient(build_app())
    r = c.get("/v1/whoami", headers={"X-API-Key": KEY})
    assert r.json() == {"kind": "machine", "role": "superadmin", "workspace_id": None}


def test_session_cookie_carries_role_and_workspace(as_user):
    as_user("client", workspace_id=42)
    c = TestClient(build_app())
    c.cookies.set(SESSION_COOKIE_NAME, "valid-session")
    assert c.get("/v1/whoami").json() == {
        "kind": "user",
        "role": "client",
        "workspace_id": 42,
    }


def test_qa_cookie_is_machine_but_only_for_safe_methods():
    c = TestClient(build_app())
    c.cookies.set(QA_COOKIE_NAME, KEY)
    assert c.get("/v1/whoami").json()["kind"] == "machine"
    # 后门 Cookie 不能用于写 —— 这是 D2 之前就有的 CSRF 防线，不能因为改造而丢
    assert c.post("/v1/write-thing").status_code == 401


def test_header_wins_over_session(as_user):
    """两个凭证同时在场时以请求头为准 —— 机器调用不该被浏览器残留的会话改写身份。"""
    as_user("client", workspace_id=1)
    c = TestClient(build_app())
    c.cookies.set(SESSION_COOKIE_NAME, "valid-session")
    assert c.get("/v1/whoami", headers={"X-API-Key": KEY}).json()["kind"] == "machine"


def test_no_credentials_is_401():
    c = TestClient(build_app())
    r = c.get("/v1/whoami")
    assert r.status_code == 401
    # 提示要覆盖全部通道，否则用会话登录的人看到「缺 X-API-Key」会一头雾水
    assert "X-API-Key" in r.json()["detail"]
    assert "/v1/auth/login" in r.json()["detail"]


def test_expired_or_bogus_session_is_401(as_user):
    as_user("operator")
    c = TestClient(build_app())
    c.cookies.set(SESSION_COOKIE_NAME, "revoked-or-expired")
    assert c.get("/v1/whoami").status_code == 401


def test_login_path_is_public():
    from app.core.security import PUBLIC_PATHS

    assert "/v1/auth/login" in PUBLIC_PATHS, "登录接口自己必须免鉴权，否则没人登得进来"


# ---------- 角色 ----------


@pytest.mark.parametrize(
    "role,can_write,is_admin",
    [("superadmin", True, True), ("operator", True, False), ("client", False, False)],
)
def test_role_capabilities(as_user, role, can_write, is_admin):
    as_user(role, workspace_id=1 if role == "client" else None)
    c = TestClient(build_app())
    c.cookies.set(SESSION_COOKIE_NAME, "valid-session")

    assert (c.post("/v1/write-thing").status_code == 200) is can_write
    assert (c.post("/v1/admin-thing").status_code == 200) is is_admin


def test_client_write_is_403_not_401(as_user):
    """已登录但没权限 = 403。返回 401 会让前端以为该重新登录，陷入登录循环。"""
    as_user("client", workspace_id=1)
    c = TestClient(build_app())
    c.cookies.set(SESSION_COOKIE_NAME, "valid-session")
    assert c.post("/v1/write-thing").status_code == 403


def test_machine_can_do_everything():
    c = TestClient(build_app())
    h = {"X-API-Key": KEY}
    assert c.post("/v1/write-thing", headers=h).status_code == 200
    assert c.post("/v1/admin-thing", headers=h).status_code == 200


# ---------- 可见范围 ----------


def test_only_client_is_workspace_scoped():
    from app.api.deps import visible_workspace_id

    assert visible_workspace_id(Principal("user", role="client", workspace_id=9)) == 9
    assert visible_workspace_id(Principal("user", role="operator", workspace_id=9)) is None
    assert visible_workspace_id(Principal("user", role="superadmin")) is None
    assert visible_workspace_id(Principal("machine")) is None


# ---------- fail-closed ----------


def test_anonymous_never_silently_sees_everything():
    """匿名不能落到「None = 看全部」那条路上。

    visible_workspace_id 用 None 表示「不受限」，所以任何「本该受限却拿不到
    workspace」的情况都必须显式拒绝，否则就是放行全部。
    """
    from fastapi import HTTPException

    from app.api.deps import visible_workspace_id
    from app.core.security import ANONYMOUS

    with pytest.raises(HTTPException) as exc:
        visible_workspace_id(ANONYMOUS)
    assert exc.value.status_code == 401


def test_client_without_workspace_is_denied_not_unscoped():
    """角色是 client 却没有 workspace —— 建号接口拦得住，直接改库造得出。

    这种行若按「None = 看全部」处理，就变成一个能看全部数据的客户账号。
    """
    from fastapi import HTTPException

    from app.api.deps import visible_workspace_id

    broken = Principal(kind="user", user_id=1, role="client", workspace_id=None)
    with pytest.raises(HTTPException) as exc:
        visible_workspace_id(broken)
    assert exc.value.status_code == 403
