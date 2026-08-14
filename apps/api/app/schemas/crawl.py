from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


#: 已知平台 = ``platform`` 列的合法取值。**注意它不等于「能跑」** ——
#: 能不能跑要问 ``registry.is_runnable``（见 registry 模块文档）。
#: 保留这个名字是为了不动既有引用；取值从注册表派生，避免两处漂移。
from app.providers.registry import known_codes as _known_codes  # noqa: E402

ALLOWED_PLATFORMS = _known_codes()


class CrawlJobCreate(BaseModel):
    prompt_id: int
    platform: str = "deepseek"
    samples: int = Field(1, ge=1, le=10)


class CrawlJobOut(BaseModel):
    id: int
    prompt_id: int
    platform: str
    status: str
    sample_index: int
    error_message: Optional[str] = None
    #: P2-08 失败分类：``timeout`` / ``rate_limited`` / ``login_required`` /
    #: ``platform_unavailable`` / ``parse_error`` / ``worker_died`` / ``unknown``。
    #: **``null`` 表示「还没失败过」**，不表示「失败了但没认出来」——
    #: 后者是 ``unknown``，两者的排查方向完全不同
    failure_kind: Optional[str] = None
    #: P2-16 已消耗的尝试次数。``attempt > 1 且 status='success'``
    #: 就是「重试之后成功的」
    attempt: Optional[int] = None
    #: P2-16 下次可被领取的时刻。**有值且在未来 = 正在退避等重试**。
    #: 退避中的 job 状态仍是 ``pending``，靠这个字段才能和「还没轮到」分开
    next_attempt_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    response_id: Optional[int] = None

    model_config = {"from_attributes": True}


class CrawlJobListOut(BaseModel):
    items: List[CrawlJobOut]
    total: int


class CrawlJobDetailOut(CrawlJobOut):
    prompt_text: Optional[str] = None
    response: Optional["RawResponseOut"] = None


class CitationOut(BaseModel):
    id: int
    cite_index: Optional[int] = None
    url: str
    domain: str
    title: Optional[str] = None
    snippet: Optional[str] = None

    model_config = {"from_attributes": True}


class MentionOut(BaseModel):
    id: int
    brand_id: int
    mentioned: bool
    mention_type: str
    position_bucket: Optional[str] = None
    #: 出场顺位（1-based，仅 body 命中有值）。**是位置事实，不是推荐名次** ——
    #: 且只在被监测品牌集合内排序，见 services/annotate.assign_position_ranks
    position_rank: Optional[int] = None
    evidence_snippet: Optional[str] = None
    #: 首次命中在 full_text 里的下标，可直接切原文 → 前端做命中处内联高亮。
    #: citation_only 命中时为 null（正文里没出现）。
    first_offset: Optional[int] = None
    #: 实际命中的别名，用于展示「靠哪个别名命中的」
    matched_term: Optional[str] = None

    model_config = {"from_attributes": True}


class RawResponseOut(BaseModel):
    id: int
    job_id: int
    platform: str
    prompt_text: str
    full_text: str
    html_path: Optional[str] = None
    screenshot_path: Optional[str] = None
    raw_json: Optional[Dict[str, Any]] = None
    latency_ms: Optional[int] = None
    answer_status: Optional[str] = None
    annotator_version: Optional[str] = None
    created_at: datetime
    citations: List[CitationOut] = Field(default_factory=list)
    mentions: List[MentionOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class RawResponseListOut(BaseModel):
    items: List[RawResponseOut]
    total: int


class RawResponseSummaryOut(BaseModel):
    """列表用的轻量投影 —— **没有 full_text，也没有 raw_json**。

    单开一个模型而不是把 ``RawResponseOut.full_text`` 改成可选：
    「有时有有时没有」的字段会让类型撒谎，前端拿到 undefined 时不会报错，
    只会渲染出一片空白。这里少的字段在类型上就是不存在的。

    ``text_preview`` / ``text_length`` 由 SQL 的 substr / length 算出来，
    大列根本不进 Python —— 这是这个端点存在的全部理由。
    """

    id: int
    job_id: int
    platform: str
    prompt_text: str
    #: 正文前 N 字（N = api/responses.py::PREVIEW_CHARS），列表里给个人眼锚点
    text_preview: str
    #: 正文总字数。配合 preview 让「这条被截断了」变成可判断的事实
    text_length: int
    screenshot_path: Optional[str] = None
    latency_ms: Optional[int] = None
    answer_status: Optional[str] = None
    annotator_version: Optional[str] = None
    created_at: datetime
    #: 逐品牌标注照常给全 —— 它是列表里唯一有结论的东西，且体量比 full_text 小两个量级
    mentions: List[MentionOut] = Field(default_factory=list)


class RawResponseSummaryListOut(BaseModel):
    items: List[RawResponseSummaryOut]
    total: int


class WorkerRunOut(BaseModel):
    processed: int
    job_ids: List[int]
