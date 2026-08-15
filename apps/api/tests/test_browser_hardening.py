"""浏览器指纹加固（P2-06a）。纯函数，不需要 playwright，本机可跑。

数值全部来自 2026-08-15 在采集节点容器里的实测（Playwright 1.49.1）：

    旧 headless：webdriver=True  plugins=0  window.chrome=undefined
                 UA=…HeadlessChrome/131.0.6778.33…
    新 headless：webdriver=False plugins=5  window.chrome=object
                 UA=…HeadlessChrome/131.0.0.0…
"""
from __future__ import annotations

from app.providers.browser import (
    CHROMIUM_CHANNEL,
    HARDENED_ARGS,
    IGNORED_DEFAULT_ARGS,
    context_kwargs,
    launch_kwargs,
    strip_headless_marker,
)


# ------------------------------------------------------------------ UA


def test_strip_headless_marker_matches_real_chrome_exactly():
    """新 headless 报 `HeadlessChrome/131.0.0.0`，换掉标记正好等于真实 Chrome
    在 UA Reduction 之后的输出 —— **不需要自己编版本号**。"""
    raw = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
           "HeadlessChrome/131.0.0.0 Safari/537.36")
    got = strip_headless_marker(raw)
    assert "Headless" not in got
    assert got == ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/131.0.0.0 Safari/537.36")


def test_strip_headless_marker_leaves_a_normal_ua_alone():
    ua = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/131.0.0.0 Safari/537.36")
    assert strip_headless_marker(ua) == ua


def test_strip_headless_marker_survives_empty():
    """读不到 UA 时不能炸 —— 加固是可选项，不是必需品。"""
    assert strip_headless_marker("") == ""


# -------------------------------------------------------------- 启动参数


def test_launch_uses_new_headless_by_default():
    """`channel="chromium"` 是这次唯一「白送」的一项：
    plugins 与 window.chrome 全靠它，省掉整个 stealth 注入层。"""
    assert launch_kwargs()["channel"] == CHROMIUM_CHANNEL


def test_launch_disables_the_automation_broadcast():
    kw = launch_kwargs()
    assert "--disable-blink-features=AutomationControlled" in kw["args"]
    assert "--enable-automation" in kw["ignore_default_args"]


def test_fallback_drops_the_channel_not_the_hardening():
    """老镜像没有 chromium channel 时回落旧 headless ——
    但**参数加固不能一起丢掉**，否则 webdriver 又变回 True。"""
    kw = launch_kwargs(use_new_headless=False)
    assert "channel" not in kw
    assert kw["args"] == HARDENED_ARGS
    assert kw["ignore_default_args"] == IGNORED_DEFAULT_ARGS


def test_launch_kwargs_does_not_share_mutable_state():
    """两次调用互不污染 —— 返回同一个 list 对象的话，
    调用方 append 一个参数会悄悄改掉全局默认。"""
    a, b = launch_kwargs(), launch_kwargs()
    a["args"].append("--boom")
    assert "--boom" not in b["args"]
    assert "--boom" not in HARDENED_ARGS


# -------------------------------------------------------------- context


def test_context_carries_locale_and_timezone():
    """时区必须跟着采集出口 —— 见 2026-08-15「IP 在长沙、时区在伦敦」那次。"""
    kw = context_kwargs(user_agent=None)
    assert kw["locale"] == "zh-CN"
    assert kw["timezone_id"] == "Asia/Shanghai"
    assert kw["viewport"]["width"] > 0


def test_context_omits_user_agent_when_unknown():
    """读不到 UA 就不覆盖，而不是塞一个编出来的 —— 编错了是新破绽。"""
    assert "user_agent" not in context_kwargs(user_agent=None)


def test_context_sets_user_agent_when_known():
    kw = context_kwargs(user_agent="Mozilla/5.0 … Chrome/131.0.0.0 Safari/537.36")
    assert "Headless" not in kw["user_agent"]


def test_timezone_is_overridable_for_the_cold_standby():
    """切 VPS 冷备时出口变新加坡，时区要跟着改。"""
    kw = context_kwargs(user_agent=None, timezone_id="Asia/Singapore")
    assert kw["timezone_id"] == "Asia/Singapore"
