"""`CrawlJobOut` 的重试三字段（P2-16 / P2-08）。纯 schema，不需要数据库。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.schemas.crawl import CrawlJobOut

NOW = datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc)


def _base(**over):
    data = {
        "id": 1,
        "prompt_id": 2,
        "platform": "deepseek",
        "status": "pending",
        "sample_index": 1,
        "created_at": NOW,
    }
    data.update(over)
    return data


def test_three_fields_default_to_none():
    """老调用方不带这几个字段照样能构造 —— 它们全是可选的。"""
    out = CrawlJobOut(**_base())
    assert out.failure_kind is None
    assert out.attempt is None
    assert out.next_attempt_at is None


def test_backoff_state_is_distinguishable_from_not_yet_claimed():
    """两条 job 都是 `pending`。前端要能分出「在等退避」和「还没轮到」——
    不新增 `retry_wait` 状态值的全部代价就压在这个字段上。"""
    waiting = CrawlJobOut(**_base(next_attempt_at=NOW + timedelta(seconds=60), attempt=1))
    queued = CrawlJobOut(**_base())

    assert waiting.status == queued.status == "pending"
    assert waiting.next_attempt_at is not None
    assert queued.next_attempt_at is None


def test_retried_then_succeeded_is_queryable():
    """`attempt > 1 且 status='success'` = 重试之后成功的。
    有这个信号就不必另建一张表记重试历史。"""
    out = CrawlJobOut(**_base(status="success", attempt=2))
    assert out.attempt > 1 and out.status == "success"
