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


class WorkerRunOut(BaseModel):
    processed: int
    job_ids: List[int]
