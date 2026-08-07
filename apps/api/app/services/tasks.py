from __future__ import annotations

from typing import Dict

# job 状态优先级：只要还有没跑完的，run 就没跑完
_UNFINISHED = ("running", "pending")


def derive_run_status(counts: Dict[str, int]) -> str:
    """由 job 状态计数派生 run 状态。

    **不落库。** 存一份就要有人同步，而 job 状态在 worker 里变、
    run 在 API 里变，两者迟早不一致 —— 而一个不一致的状态列
    比没有状态列更糟，因为它看起来权威。

    ``partial`` 是独立一档：部分成功报成 success 会让人以为
    35 条都在，实际分母少了一截，所有比率静默偏高。
    """
    total = sum(counts.values())
    if total == 0:
        return "empty"
    for st in _UNFINISHED:
        if counts.get(st, 0) > 0:
            return st
    ok = counts.get("success", 0)
    if ok == total:
        return "success"
    if ok == 0:
        return "failed"
    return "partial"
