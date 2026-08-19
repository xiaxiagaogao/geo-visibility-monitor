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


# ------------------------------------------------- 证据截图（P2-34 第 4 步）
#
# 迁到大陆节点之后截图关了两个月，而**关的方式是把 None 写死进 provider**
# （`qianwen_web` 的 `screenshot_path=None,  # 节点上截图关闭`）。
# 于是 P2-34 把回传链路做完之后，千问那条线仍然一张图都没有 ——
# 配置说「开着」，代码说「关着」，而没有任何地方报错。
#
# 教训：**「暂时关掉」要关在配置上，不要关在代码里。**


class _StubPage:
    """记下 screenshot 被怎么调的。不需要 playwright。"""

    def __init__(self, boom=False):
        self.calls = []
        self.boom = boom

    def screenshot(self, **kw):
        self.calls.append(kw)
        if self.boom:
            raise RuntimeError("target closed")


def test_evidence_is_captured_when_a_directory_is_configured(tmp_path):
    from app.providers.browser import capture_evidence

    page = _StubPage()
    path = capture_evidence(page, str(tmp_path), platform="tongyi")

    assert path and path.endswith(".png") and "tongyi" in path
    assert page.calls[0]["full_page"] is True, "整页才看得到完整答案（表格/列表会被裁）"
    assert page.calls[0]["type"] == "png"


def test_no_directory_means_no_screenshot_and_no_call(tmp_path):
    """隧道模式把 SCREENSHOT_DIR 置空 —— 那时连截都不该截。"""
    from app.providers.browser import capture_evidence

    page = _StubPage()
    assert capture_evidence(page, "", platform="tongyi") is None
    assert capture_evidence(page, None, platform="tongyi") is None
    assert page.calls == []


def test_a_failed_screenshot_never_costs_us_the_answer(tmp_path):
    """**证据图没了，不该把一条真答案一起丢掉。**

    截图发生在答案已经拿到之后。让它抛出去，整条 job 会变成 failed，
    然后按 P2-16 重试 —— 用三倍配额去换一张图，方向反了。
    """
    from app.providers.browser import capture_evidence

    assert capture_evidence(_StubPage(boom=True), str(tmp_path), platform="tongyi") is None


def test_two_shots_in_the_same_second_do_not_collide(tmp_path):
    """文件名撞了就是后一张盖掉前一张，而证据页照样显示 —— 静默错配。"""
    from app.providers.browser import capture_evidence

    a = capture_evidence(_StubPage(), str(tmp_path), platform="tongyi")
    b = capture_evidence(_StubPage(), str(tmp_path), platform="tongyi")
    assert a != b
