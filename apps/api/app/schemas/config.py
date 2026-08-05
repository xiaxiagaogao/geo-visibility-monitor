from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel


class MetricsConfigOut(BaseModel):
    """口径配置下发（防前端硬编码）."""

    answer_status_values: List[str]
    valid_denominator: str
    mention_types: List[str]
    position_buckets: List[str]
    default_composite_weights: Dict[str, float]
    annotator_version: str
    crawl_mode_default_hint: str


class PlatformOut(BaseModel):
    """一个平台的可用性。

    ``available`` 的语义是**「现在建任务能不能跑完」**，不是「代码里有没有这个常量」。
    前端据此渲染 chip 的可点 / 灰显，**不要再硬编码平台清单**。
    """

    code: str
    label: str
    #: 现在建任务能否跑完（fake 模式下已知平台都为 true）
    available: bool
    #: 是否有 real Provider —— 与 available 分开，便于区分「没接」和「在跑假数据」
    implemented: bool
    #: 不可用的原因，或可用但需要提醒的说明；可用且无提醒时为 null
    note: Optional[str] = None


class PlatformListOut(BaseModel):
    items: List[PlatformOut]
    crawl_mode: str
