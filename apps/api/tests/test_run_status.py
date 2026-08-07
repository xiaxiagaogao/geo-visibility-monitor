"""run 状态由其下 job 派生 —— 纯函数，不需要数据库。"""
from __future__ import annotations

from app.services.tasks import derive_run_status


def test_all_success():
    assert derive_run_status({"success": 35}) == "success"


def test_any_pending_is_pending():
    assert derive_run_status({"success": 30, "pending": 5}) == "pending"


def test_any_running_beats_pending():
    """running 优先于 pending —— 用户关心「正在跑」，不关心队列里还剩几个。"""
    assert derive_run_status({"pending": 3, "running": 1, "success": 10}) == "running"


def test_all_failed():
    assert derive_run_status({"failed": 12}) == "failed"


def test_partial_is_its_own_state():
    """部分成功不能报成 success —— 分母少了一截，比率会静默偏高。"""
    assert derive_run_status({"success": 30, "failed": 5}) == "partial"


def test_no_jobs_is_empty():
    """建了 run 却一个 job 都没有 —— 是配置问题（提问集为空），不是成功。"""
    assert derive_run_status({}) == "empty"
