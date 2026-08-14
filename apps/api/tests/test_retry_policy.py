"""自动退避重试的决策（P2-16）。纯函数，不需要数据库。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.failure_kinds import (
    LOGIN_REQUIRED,
    PARSE_ERROR,
    RATE_LIMITED,
    TIMEOUT,
    UNKNOWN,
    WORKER_DIED,
)
from app.services.retry_policy import compute_backoff_sec, plan_next_attempt

NOW = datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc)


class _Settings:
    """只带 plan_next_attempt 认的那几个字段的替身。"""

    def __init__(self, **kw):
        self.crawl_auto_retry_enabled = kw.get("enabled", True)
        self.crawl_max_attempts = kw.get("max_attempts", 3)
        self.crawl_retry_base_sec = kw.get("base", 30.0)
        self.crawl_retry_max_sec = kw.get("cap", 300.0)
        self.crawl_retry_jitter = kw.get("jitter", 0.0)


# ---------------------------------------------------------------- 曲线本身


def test_curve_is_exponential_from_base():
    kw = dict(base_sec=30.0, max_sec=300.0)
    assert compute_backoff_sec(1, **kw) == 30.0
    assert compute_backoff_sec(2, **kw) == 60.0
    assert compute_backoff_sec(3, **kw) == 120.0


def test_curve_is_capped():
    kw = dict(base_sec=30.0, max_sec=300.0)
    assert compute_backoff_sec(5, **kw) == 300.0
    assert compute_backoff_sec(50, **kw) == 300.0


def test_curve_is_monotonic_up_to_the_cap():
    kw = dict(base_sec=30.0, max_sec=300.0)
    seq = [compute_backoff_sec(n, **kw) for n in range(1, 12)]
    assert seq == sorted(seq)


def test_jitter_zero_is_fully_deterministic():
    """测试要能钉住结果，所以抖动必须可关。"""
    kw = dict(base_sec=30.0, max_sec=300.0, jitter_ratio=0.0)
    assert compute_backoff_sec(1, **kw) == compute_backoff_sec(1, **kw) == 30.0


@pytest.mark.parametrize("r,expected", [(0.0, 24.0), (0.5, 30.0), (1.0, 36.0)])
def test_jitter_spans_plus_minus_ratio(r, expected):
    got = compute_backoff_sec(
        1, base_sec=30.0, max_sec=300.0, jitter_ratio=0.2, rand=lambda: r
    )
    assert got == pytest.approx(expected)


def test_jitter_applies_after_the_cap():
    """封顶指的是曲线本身。抖动若在封顶之前，到了封顶处就只能往下抖 ——
    单边抖动等于没抖，而「同批 job 同时到期再一起撞」正是要避免的。"""
    got = compute_backoff_sec(
        99, base_sec=30.0, max_sec=300.0, jitter_ratio=0.2, rand=lambda: 1.0
    )
    assert got == pytest.approx(360.0)


def test_never_returns_zero_or_negative():
    """0 等于「立刻可领」，退避就白做了。"""
    got = compute_backoff_sec(
        1, base_sec=0.0, max_sec=300.0, jitter_ratio=0.9, rand=lambda: 0.0
    )
    assert got >= 1.0


# ------------------------------------------------------------ 重试与否的决策


def test_retryable_failure_is_rescheduled():
    when = plan_next_attempt(kind=TIMEOUT, attempt=1, settings=_Settings(), now=NOW)
    assert when == NOW + timedelta(seconds=30)


def test_rate_limited_is_also_rescheduled():
    assert plan_next_attempt(
        kind=RATE_LIMITED, attempt=1, settings=_Settings(), now=NOW
    ) is not None


@pytest.mark.parametrize("kind", [LOGIN_REQUIRED, PARSE_ERROR, WORKER_DIED, UNKNOWN])
def test_non_retryable_kinds_are_terminal(kind):
    assert plan_next_attempt(kind=kind, attempt=1, settings=_Settings(), now=NOW) is None


def test_attempts_are_exhausted_and_never_requeued_again():
    """**这条是「重试耗尽后不能无限重排」的落点。**"""
    s = _Settings(max_attempts=3)
    assert plan_next_attempt(kind=TIMEOUT, attempt=1, settings=s, now=NOW) is not None
    assert plan_next_attempt(kind=TIMEOUT, attempt=2, settings=s, now=NOW) is not None
    assert plan_next_attempt(kind=TIMEOUT, attempt=3, settings=s, now=NOW) is None
    assert plan_next_attempt(kind=TIMEOUT, attempt=99, settings=s, now=NOW) is None


def test_disabled_switch_makes_everything_terminal():
    """开关是回滚手段：改环境变量重启即可回到「只分类不重试」，不必 git revert。"""
    s = _Settings(enabled=False)
    assert plan_next_attempt(kind=TIMEOUT, attempt=1, settings=s, now=NOW) is None


def test_max_attempts_one_means_no_retry_at_all():
    """把上限调成 1 = 关掉重试的另一种写法，不该出现 attempt 1 还排一次。"""
    s = _Settings(max_attempts=1)
    assert plan_next_attempt(kind=TIMEOUT, attempt=1, settings=s, now=NOW) is None


def test_backoff_grows_between_attempts():
    s = _Settings(max_attempts=5)
    first = plan_next_attempt(kind=TIMEOUT, attempt=1, settings=s, now=NOW)
    second = plan_next_attempt(kind=TIMEOUT, attempt=2, settings=s, now=NOW)
    assert second > first
