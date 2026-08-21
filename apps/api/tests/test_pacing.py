"""抓取节奏打散（P2-38 的前置）。纯函数，不需要网络也不真 sleep。

## 为什么要有它

run 298 逐条量出来的起点间隔：**46 / 46 / 42 / 40 / 52 / 42 / 53 / 43 秒。**
一个真人不会这样用。而 `CRAWL-INTEL.md` §4.1 的结论是：
**被盯上的不是量（我们每天才 10–20 条），是规律性** —— 固定时段、固定提问集、
固定间隔。检测耐久度排序是 API < 渲染 < TLS < **行为**，而我们输在最后一层。

## 这个模块**不声称**能模仿人

它只做一件能说清楚的事：**把一个常数变成一个分布**。
固定 41 秒的心跳本身就是一个指纹，去掉它是确定的收益；
而「像不像人」需要真人基线做对照，我们没有，所以不去声称。

**默认关**（min=max=0）。开关同时是回滚手段：改环境变量重启即可，
不必 git revert（`PHASE2.md` §6 规矩 1）。
"""
from __future__ import annotations

import random

import pytest

from app.services.pacing import next_pause_sec


class _S:
    def __init__(self, lo=0.0, hi=0.0):
        self.crawl_pace_min_sec = lo
        self.crawl_pace_max_sec = hi


def test_disabled_by_default_costs_nothing():
    """**只加不改**：不配就是现在的行为，一秒都不多等。"""
    assert next_pause_sec(_S()) == 0.0


def test_pause_stays_inside_the_configured_range():
    rng = random.Random(0)
    for _ in range(200):
        assert 20.0 <= next_pause_sec(_S(20, 90), rng) <= 90.0


def test_the_whole_point_is_that_it_varies():
    """**固定间隔本身就是指纹。** 这条钉的就是「它不是个常数」。"""
    rng = random.Random(1)
    seen = {round(next_pause_sec(_S(20, 90), rng), 3) for _ in range(50)}

    assert len(seen) > 40, f"只取到 {len(seen)} 个不同的值，那还是个心跳"


def test_a_single_value_range_is_honoured_not_rejected():
    """min == max 是「我就要固定间隔」，合法 —— 只是那正是我们要避免的。"""
    assert next_pause_sec(_S(30, 30)) == 30.0


def test_a_reversed_range_does_not_explode():
    """配反了是人的手误。**别抛异常** —— 它跑在采集循环里，
    崩掉的代价是整晚不采，比等错时长严重得多。"""
    v = next_pause_sec(_S(90, 20), random.Random(2))
    assert 20.0 <= v <= 90.0


def test_a_negative_setting_is_treated_as_off():
    """负数睡不了，当成关掉。"""
    assert next_pause_sec(_S(-5, -1)) == 0.0


def test_only_a_max_still_spreads_from_zero():
    """只配上限时下限按 0 算 —— 比报错友好，且语义明确。"""
    rng = random.Random(3)
    vals = [next_pause_sec(_S(0, 60), rng) for _ in range(30)]
    assert all(0 <= v <= 60 for v in vals)
    assert len(set(round(v, 3) for v in vals)) > 25


@pytest.mark.parametrize("lo,hi", [(0, 0), (0, 0.0)])
def test_zero_range_is_off_not_a_zero_length_sleep(lo, hi):
    assert next_pause_sec(_S(lo, hi)) == 0.0
