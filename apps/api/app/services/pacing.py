"""抓取节奏打散（P2-38 的前置）。**纯函数。**

## 为什么要有它

run 298 逐条量出来的起点间隔是 **46 / 46 / 42 / 40 / 52 / 42 / 53 / 43 秒**——
一个真人不会这样用。而 `CRAWL-INTEL.md` §4.1 的结论是：**被盯上的不是量**
（我们每天才 10–20 条），**是规律性**：固定时段、固定提问集、固定间隔。
检测耐久度排序是 API < 渲染 < TLS < **行为**，而我们输在最后一层。

## 这个模块不声称能模仿人

它只做一件能说清楚的事：**把一个常数变成一个分布**。固定 41 秒的心跳本身
就是一个指纹，去掉它是确定的收益；而「像不像人」需要真人使用基线来对照，
**我们没有那个基线，所以不去声称**（`CRAWL-INTEL.md` §3.4「明确没找到的」
第一条就是这类参数）。

用均匀分布而不是什么长尾模型，也是同一个理由：**我们没有依据去挑一个更像的形状**，
挑了就是在编。均匀分布至少是诚实的、可解释的、参数一眼能看懂。

## 开关

`CRAWL_PACE_MIN_SEC` / `CRAWL_PACE_MAX_SEC`，**默认 0 = 关**，
行为与加它之前一个字节不差。开关同时是回滚手段：改环境变量重启即可，
不必 git revert（`PHASE2.md` §6 规矩 1）。
"""
from __future__ import annotations

import random
from typing import Optional

_shared = random.Random()


def next_pause_sec(settings, rng: Optional[random.Random] = None) -> float:
    """两条 job 之间该等多久（秒）。``0`` = 不等（默认）。

    **绝不抛异常。** 它跑在采集循环里 —— 崩掉的代价是整晚不采，
    比等错时长严重得多。所以配反了（min > max）就交换，配了负数就当关掉。
    """
    lo = _clean(getattr(settings, "crawl_pace_min_sec", 0.0))
    hi = _clean(getattr(settings, "crawl_pace_max_sec", 0.0))
    if lo > hi:
        lo, hi = hi, lo          # 配反了是手误，不是让它崩的理由
    if hi <= 0:
        return 0.0
    if lo == hi:
        return float(lo)         # 「我就要固定间隔」是合法的，只是不推荐
    return (rng or _shared).uniform(lo, hi)


def _clean(v) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return f if f > 0 else 0.0
