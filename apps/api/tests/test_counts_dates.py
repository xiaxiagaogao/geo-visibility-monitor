"""counts 的时间区间解析（L3 前端筛选会直接依赖）。"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.services.counts import _parse_dt


def test_none_and_empty():
    assert _parse_dt(None) is None
    assert _parse_dt("") is None


def test_date_only_from_is_start_of_day():
    assert _parse_dt("2026-08-01") == datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)


def test_date_only_to_covers_the_whole_day():
    """曾经的 bug：end 参数被声明却从未使用，to=2026-08-01 排除了整个 8/1。"""
    dt = _parse_dt("2026-08-01", end=True)
    assert dt == datetime(2026, 8, 1, 23, 59, 59, 999999, tzinfo=timezone.utc)


def test_explicit_time_is_not_rounded():
    """给了具体时刻就按原样，不要自作主张补到当天末尾。"""
    dt = _parse_dt("2026-08-01T09:30:00", end=True)
    assert dt == datetime(2026, 8, 1, 9, 30, tzinfo=timezone.utc)


def test_zulu_suffix():
    assert _parse_dt("2026-08-01T12:00:00Z") == datetime(
        2026, 8, 1, 12, 0, tzinfo=timezone.utc
    )


def test_naive_input_is_treated_as_utc():
    assert _parse_dt("2026-08-01T12:00:00").tzinfo == timezone.utc


def test_offset_aware_input_is_preserved():
    dt = _parse_dt("2026-08-01T12:00:00+08:00")
    assert dt.utcoffset().total_seconds() == 8 * 3600


def test_invalid_raises_400():
    with pytest.raises(HTTPException) as exc:
        _parse_dt("not-a-date")
    assert exc.value.status_code == 400
