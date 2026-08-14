"""自动退避重试的决策（P2-16）。纯函数，不碰数据库。

**为什么退避必须落成一个「什么时候才可以再领」的时刻，而不是在进程里 sleep：**

1. ``run_once`` 是串行 for 循环。进程内 sleep 会把整批串起来 ——
   头两条各睡 30/60 秒，后面明明可以跑的 job 白等几分钟。
2. sleep 期间 job 还是 ``running``，``CRAWL_STUCK_JOB_SEC`` 那套僵死回收
   照常计时（超时 120s + 退避 90s + 再超时 120s 就快撞上 600s），
   撞上就被收成 ``failed``，而回收写的 error_message 会把真正的失败原因盖掉。
3. worker 一重启就全丢。采集节点不是独占机器，重启是现实。

落库之后这三条同时消失：退避中的 job 状态回 ``pending``，claim 直接跳过它去领
下一条 —— 不占 worker，也不会被僵死回收误伤。
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Callable, Optional

from app.services.failure_kinds import is_retryable

#: 指数部分的封顶，纯防御 —— attempt 不可能大到这里，但 ``2 ** attempt``
#: 在 attempt 失控时会算出一个荒唐的大数
_MAX_EXPONENT = 16


def compute_backoff_sec(
    attempt: int,
    *,
    base_sec: float,
    max_sec: float,
    jitter_ratio: float = 0.0,
    rand: Callable[[], float] = random.random,
) -> float:
    """``attempt`` 次尝试都失败之后，还要等多久才可以再试。

    ``attempt`` 是**已消耗的次数**（1-based）：第 1 次失败后等 ``base``，
    第 2 次失败后等 ``base * 2``，以此类推，到 ``max_sec`` 封顶。

    抖动是**在封顶之后**乘上去的，所以实际上限是 ``max_sec * (1 + jitter)``。
    这么排是为了让「封顶」这个参数指的是曲线本身，而不是一个会被抖动打破的硬上限
    —— 后者会让抖动在封顶处变成单边（只能往下抖），失去意义。

    ``rand`` 可注入，测试里传一个确定的函数就能钉住结果。
    """
    steps = max(0, min(attempt - 1, _MAX_EXPONENT))
    delay = min(base_sec * (2**steps), max_sec)
    if jitter_ratio:
        delay *= 1.0 + jitter_ratio * (2.0 * rand() - 1.0)
    # 绝不返回 0 或负数：那等于「立刻可领」，退避就白做了
    return max(1.0, delay)


def plan_next_attempt(
    *,
    kind: str,
    attempt: int,
    settings,
    now: datetime,
    rand: Callable[[], float] = random.random,
) -> Optional[datetime]:
    """这条 job 下次可以被领取的时刻；``None`` = **不再自动重试，终态 failed**。

    ``attempt`` 是本次失败之后已消耗的尝试次数。

    四道关，任何一道不过就返回 ``None``：

    1. 开关没开（``CRAWL_AUTO_RETRY_ENABLED``）
    2. 这类失败不该重试（见 ``failure_kinds.RETRYABLE_KINDS``）
    3. 次数已耗尽 —— **这条就是「不能无限重排」的落点**
    4. 上面都过了，才算退避时刻
    """
    if not getattr(settings, "crawl_auto_retry_enabled", False):
        return None
    if not is_retryable(kind):
        return None
    if attempt >= settings.crawl_max_attempts:
        return None
    delay = compute_backoff_sec(
        attempt,
        base_sec=settings.crawl_retry_base_sec,
        max_sec=settings.crawl_retry_max_sec,
        jitter_ratio=settings.crawl_retry_jitter,
        rand=rand,
    )
    return now + timedelta(seconds=delay)
