"""失败分类（P2-08）。纯函数，不需要数据库。

用例里的报错文本**全部抄自现行代码的真实字符串**，不是编的：

- ``Page.goto: Timeout 120000ms exceeded.``  Playwright（已在采集节点容器里核过）
- ``crawl timed out after 165s``             ``crawl_runner.process_job``
- ``DeepSeek appears to require login. ...`` ``providers/deepseek_web``
- ``empty answer from DeepSeek (UI changed or blocked)``  同上
- ``real crawl not implemented for platform=doubao; ...``  ``providers/registry``
"""
from __future__ import annotations

import pytest

from app.providers.deepseek_web import DeepSeekLoginRequired
from app.services.failure_kinds import (
    ALL_KINDS,
    LOGIN_REQUIRED,
    PARSE_ERROR,
    PLATFORM_UNAVAILABLE,
    RATE_LIMITED,
    RETRYABLE_KINDS,
    TIMEOUT,
    UNKNOWN,
    WORKER_DIED,
    classify_failure,
    is_retryable,
)


class _FakePlaywrightTimeout(Exception):
    """冒充 ``playwright._impl._errors.TimeoutError``。

    **本机与 api 容器里都没有 playwright**（它不跑抓取），所以不能 import 真的。
    分类器本来就是按「MRO 上的模块前缀 + 类名」认的，正好可以这样测 ——
    真实类型的形状已在采集节点容器里核过：
    ``module=playwright._impl._errors  name=TimeoutError``。
    """


_FakePlaywrightTimeout.__module__ = "playwright._impl._errors"
_FakePlaywrightTimeout.__name__ = "TimeoutError"


def test_playwright_timeout_is_classified_without_importing_playwright():
    """P2-16 要解决的就是这一条：冷启动被限流时的 goto 超时。"""
    exc = _FakePlaywrightTimeout("Page.goto: Timeout 120000ms exceeded.")
    assert classify_failure(exc) == TIMEOUT
    assert is_retryable(classify_failure(exc))


def test_process_job_hard_cap_timeout():
    """``process_job`` 把 ThreadPoolExecutor 的超时转成了 RuntimeError，只剩消息可认。"""
    assert classify_failure(RuntimeError("crawl timed out after 165s")) == TIMEOUT


def test_builtin_timeout_error():
    """3.11 起 ``concurrent.futures.TimeoutError`` 就是内建 TimeoutError 的别名。"""
    assert classify_failure(TimeoutError()) == TIMEOUT


def test_login_required_is_not_retryable():
    """重试一百次也没用 —— 要人去换 storage_state。"""
    exc = DeepSeekLoginRequired(
        "DeepSeek appears to require login. "
        "Export storage_state JSON and set DEEPSEEK_STORAGE_STATE."
    )
    assert classify_failure(exc) == LOGIN_REQUIRED
    assert not is_retryable(LOGIN_REQUIRED)


def test_login_wins_over_timeout_in_the_same_message():
    """登录墙下等选择器也会超时。先判登录，否则会归成「可重试」然后白撞三次。"""
    msg = "waiting for input box: Timeout 30000ms exceeded (appears to require login)"
    assert classify_failure(RuntimeError(msg)) == LOGIN_REQUIRED


def test_platform_not_implemented():
    msg = (
        "real crawl not implemented for platform=doubao; "
        "implemented=['deepseek'] or use crawl_mode=fake"
    )
    assert classify_failure(RuntimeError(msg)) == PLATFORM_UNAVAILABLE
    assert not is_retryable(PLATFORM_UNAVAILABLE)


@pytest.mark.parametrize(
    "msg",
    [
        "HTTP 429 Too Many Requests",
        "rate limit exceeded",
        "访问过于频繁，请稍后再试",
    ],
)
def test_rate_limited_is_retryable(msg):
    assert classify_failure(RuntimeError(msg)) == RATE_LIMITED
    assert is_retryable(RATE_LIMITED)


def test_parse_error_is_not_retryable_despite_saying_blocked():
    """报错里带着「or blocked」，但它同时可能是「DeepSeek 改了 DOM」——
    那种情况下重试只会掩盖问题。"""
    exc = RuntimeError("empty answer from DeepSeek (UI changed or blocked)")
    assert classify_failure(exc) == PARSE_ERROR
    assert not is_retryable(PARSE_ERROR)


def test_unknown_is_the_fallback_and_is_not_retryable():
    """不认识的失败不自动重试 —— 否则最后留在 error_message 里的是第 3 次的报错。"""
    assert classify_failure(RuntimeError("something nobody has seen before")) == UNKNOWN
    assert classify_failure(RuntimeError("")) == UNKNOWN
    assert classify_failure(None) == UNKNOWN
    assert not is_retryable(UNKNOWN)


def test_playwright_not_installed_is_unknown_not_platform_unavailable():
    """这是部署环境的问题（跑在没装 playwright 的镜像里），不是「平台没接」。
    重试它没有意义，所以落到 unknown（不重试）是对的。"""
    msg = "playwright not installed; use crawler image or pip install playwright"
    assert classify_failure(RuntimeError(msg)) == UNKNOWN


def test_accepts_plain_string():
    """``reclaim_stuck_jobs`` 这类地方手里只有一条消息，没有异常对象。"""
    assert classify_failure("Page.goto: Timeout 120000ms exceeded.") == TIMEOUT


def test_only_timeout_and_rate_limited_are_retryable():
    """这条锁的是**清单本身**：往 RETRYABLE_KINDS 里加东西必须是自觉的决定。"""
    assert RETRYABLE_KINDS == {TIMEOUT, RATE_LIMITED}
    assert WORKER_DIED not in RETRYABLE_KINDS
    assert set(RETRYABLE_KINDS).issubset(ALL_KINDS)
