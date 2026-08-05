from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class DenominatorCounts(BaseModel):
    definition: str = "answer_status=ok"
    n_valid: int
    n_total_responses: int
    n_empty: int = 0
    n_too_short: int = 0
    n_error: int = 0
    n_unannotated: int = 0


class BrandMentionCounts(BaseModel):
    brand_id: int
    m_mentioned: int = 0
    m_body: int = 0
    m_citation_only: int = 0
    m_none: int = 0
    m_head: int = 0
    m_middle: int = 0
    m_tail: int = 0


class CountsBucket(BaseModel):
    """One aggregation bucket — integers only, no rates."""

    key: str
    denominator: DenominatorCounts
    brand: BrandMentionCounts
    competitors: List[BrandMentionCounts] = Field(default_factory=list)


class CountsResponse(BaseModel):
    """L2 counts API — frontend derives rates (L3)."""

    brand_id: int
    filters: Dict[str, Any]
    group_by: str
    # overall totals
    denominator: DenominatorCounts
    brand: BrandMentionCounts
    competitors: List[BrandMentionCounts] = Field(default_factory=list)
    # optional series when group_by != none
    series: List[CountsBucket] = Field(default_factory=list)
    note: str = "counts only; compute rates on client (L3)"


# MetricsConfigOut 已移至 app/schemas/config.py（与 PlatformOut 同处），URL 未变。
