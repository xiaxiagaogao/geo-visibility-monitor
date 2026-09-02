"""CSRF token 必须能被跨域前端拿到 —— 不需要数据库。

**根因（差点上线才发现）：** 双提交方案原本要求前端读 `geo_csrf` Cookie 回填
`X-CSRF-Token`。但分离部署下前端在 `geo.example.com`、Cookie 是
`geo-api.example.com` 下发的 host-only（`set_cookie` 不带 `domain`），
`document.cookie` **读不到它**。

而这是最坏的一类 bug：开发期走 next rewrites 代理时 Cookie 落在 localhost，
JS 读得到、验证会通过；一上生产就全线 403，且前端无从补救。

给 Cookie 加 `Domain=.example.com` 不可行 —— 同机还有 `app-a.example.com`、
`app-b.example.com` 两个不相干项目，会把会话 Cookie 发给它们。

所以改成：**响应体里带上 csrf token**。安全性与双提交等价 ——
跨站攻击者读不到这个响应体，CORS 只允许 `geo.example.com`。
Cookie 仍是服务端那一半，响应体只是前端得知这个值的通道。
"""
from __future__ import annotations

import inspect

from app.api import auth as auth_api


def test_me_out_carries_csrf():
    """login 与 me 共用 MeOut，字段加在这里两个端点都能拿到。"""
    assert "csrf_token" in auth_api.MeOut.model_fields


def test_csrf_token_is_optional():
    """machine 身份（X-API-Key）不走 Cookie，也就没有 csrf —— 不能设成必填。"""
    assert auth_api.MeOut.model_fields["csrf_token"].default is None


def test_login_returns_the_token_it_just_issued():
    """登录时下发的 csrf 与返回体里的必须是同一个值。

    各自生成一个的话，Cookie 里是 A、前端拿到 B，
    写操作会被后端判成不匹配而 403 —— 而且只在开了开关之后才显形。
    """
    src = inspect.getsource(auth_api.login)
    assert "csrf = new_csrf_token()" in src, "先生成再分别用于 Cookie 与响应体"
    assert "_set_auth_cookies(response, token, csrf)" in src
    assert "csrf_token=csrf" in src


def test_me_echoes_the_cookie_not_a_new_token():
    """me 必须回显请求里带来的那个 Cookie 值。

    每次调 /me 都新发一个的话，另一个标签页里正在用的 token 会被作废。
    """
    src = inspect.getsource(auth_api.me)
    assert "request.cookies.get(CSRF_COOKIE_NAME)" in src


def test_me_reissues_when_cookie_missing():
    """会话还在、csrf Cookie 没了 —— 要能自愈。

    不补发的话用户会卡在「登录着但所有写操作 403」，且界面上看不出原因。
    """
    src = inspect.getsource(auth_api.me)
    assert "_set_csrf_cookie" in src, "缺 Cookie 时要补发"
    # 只补 csrf 那一张，别把会话 Cookie 也重发了 —— /me 是个读接口，
    # 顺手续期会让「会话何时过期」变得不可预测。
    assert "_set_auth_cookies" not in src
