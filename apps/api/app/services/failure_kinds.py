"""失败分类（P2-08），以及「哪些失败值得自动重试」（P2-16 的前提）。

``failed`` 原本是一个笼统状态。但「登录态过期 / 冷启动超时 / 被限流 / 平台没接 /
解析失败」的排查方向完全不同 —— 混成一个词等于没有信息。

分类和自动重试是同一件事的两面：重试一个登录态过期的 job 一百次也没用
（要人去换 ``storage_state``），而不重试一个冷启动超时的 job
就等于每次 run 丢掉头几条。所以两者一起做。

**判定顺序是「异常类型 → 消息模式 → unknown」，类型优先。** 字符串匹配是脆的
（Playwright 改一版文案就能让它静默失效），而异常类型是稳的。消息模式只是兜底。
"""
from __future__ import annotations

from typing import Optional, Union

from app.providers.deepseek_web import DeepSeekLoginRequired

#: 冷启动限流、``Page.goto`` 超时、``process_job`` 的硬上限超时
TIMEOUT = "timeout"
#: 明确的限流信号（429 / 「访问过于频繁」）
RATE_LIMITED = "rate_limited"
#: ``storage_state`` 过期。表现是一批 job 全红
LOGIN_REQUIRED = "login_required"
#: Provider 没实现。正常情况下 ``create_jobs`` 就该挡成 400，走到这里说明是历史遗留任务
PLATFORM_UNAVAILABLE = "platform_unavailable"
#: 拿到页面了但抽不出答案（DOM 变了 / 返回空）
PARSE_ERROR = "parse_error"
#: ``reclaim_stuck_jobs`` 收的：worker 中途死了没来得及收尾
WORKER_DIED = "worker_died"
#: 兜底。**不认识的失败不自动重试**，理由见 ``RETRYABLE_KINDS``
UNKNOWN = "unknown"

ALL_KINDS = (
    TIMEOUT,
    RATE_LIMITED,
    LOGIN_REQUIRED,
    PLATFORM_UNAVAILABLE,
    PARSE_ERROR,
    WORKER_DIED,
    UNKNOWN,
)

#: 只有这两类值得自动重试。
#:
#: **``unknown`` 刻意不在里面。** 自动重试一个我们不理解的失败，是用 3 倍时间去撞
#: 同一堵墙，还会把原始信号淹掉 —— 最后留在 ``error_message`` 里的是第 3 次的报错，
#: 不是第 1 次的。分类跑一段时间之后，如果 ``unknown`` 里长期蹲着某个真该重试的
#: 模式，再把它提上来（那时你手里有真实样本，而不是猜）。
#:
#: **``worker_died`` 也不在里面。** 那是环境问题（容器被 OOM / 家宽断电 / 重新部署），
#: 自动重排会让它不被发现 —— 和 ``reclaim_stuck_jobs`` 那个 docstring 的判断一致。
#:
#: **``parse_error`` 也不在里面**，虽然它的报错里带着「or blocked」。它同时可能是
#: 「DeepSeek 改了 DOM」，那种情况下重试只会掩盖问题。
RETRYABLE_KINDS = frozenset({TIMEOUT, RATE_LIMITED})

# 消息模式一律小写子串匹配。**顺序有意义**：先判更具体的，再判更泛的 ——
# 登录墙的报错里也可能带 timeout（等选择器等超时），先判登录才不会归错类。
_LOGIN_PATTERNS = ("require login", "requires login", "storage_state", "登录", "登陆")
_PLATFORM_PATTERNS = ("not implemented for platform", "尚未接入")
_RATE_PATTERNS = (
    "429",
    "too many requests",
    "rate limit",
    "ratelimit",
    "过于频繁",
    "请求频繁",
    "稍后再试",
)
_TIMEOUT_PATTERNS = ("timeout", "timed out", "超时")
_PARSE_PATTERNS = ("empty answer", "ui changed", "解析失败")


def _has_type(exc: BaseException, module_prefix: str, name: str) -> bool:
    """按 MRO 上的「模块前缀 + 类名」认异常类型，**不 import 那个包**。

    这是为 Playwright 准备的：``api`` 容器里没装 playwright（它不跑抓取），
    在模块顶层 ``import playwright`` 会让整个 api 进程起不来。
    而 ``playwright._impl._errors.TimeoutError`` 这个类型本身是稳定的，
    走 MRO 认名字就够 —— 已在采集节点容器里核过。
    """
    for cls in type(exc).__mro__:
        if cls.__name__ == name and (cls.__module__ or "").startswith(module_prefix):
            return True
    return False


def classify_message(message: Optional[str]) -> str:
    """只看消息文本的分类。类型判不出来时的兜底，也单独可测。"""
    text = (message or "").lower()
    if not text.strip():
        return UNKNOWN
    for patterns, kind in (
        (_LOGIN_PATTERNS, LOGIN_REQUIRED),
        (_PLATFORM_PATTERNS, PLATFORM_UNAVAILABLE),
        (_RATE_PATTERNS, RATE_LIMITED),
        (_TIMEOUT_PATTERNS, TIMEOUT),
        (_PARSE_PATTERNS, PARSE_ERROR),
    ):
        if any(p in text for p in patterns):
            return kind
    return UNKNOWN


def classify_failure(exc: Union[BaseException, str, None]) -> str:
    """把一次失败归成 ``ALL_KINDS`` 里的一个。永远返回一个值，不抛异常。"""
    if exc is None:
        return UNKNOWN
    if isinstance(exc, str):
        return classify_message(exc)

    # 1) 我们自己的异常类型 —— 精确，且改名字时 import 会当场报错
    if isinstance(exc, DeepSeekLoginRequired):
        return LOGIN_REQUIRED
    # 2) Playwright 的超时（`Page.goto: Timeout 120000ms exceeded`）——
    #    P2-16 要解决的就是这一条
    if _has_type(exc, "playwright", "TimeoutError"):
        return TIMEOUT
    # 3) 内建超时。3.11 起 concurrent.futures.TimeoutError 就是它的别名，
    #    所以 process_job 那个 ThreadPoolExecutor 硬上限也走这里
    if isinstance(exc, TimeoutError):
        return TIMEOUT
    # 4) 兜底：看消息
    return classify_message(str(exc))


def is_retryable(kind: Optional[str]) -> bool:
    return kind in RETRYABLE_KINDS
