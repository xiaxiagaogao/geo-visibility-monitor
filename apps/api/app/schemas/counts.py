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
    # m_head / m_middle / m_tail 是 position_bucket（篇幅三等分）
    m_head: int = 0
    m_middle: int = 0
    m_tail: int = 0
    #: position_rank == 1 的样本数 —— 前端的首位提及率 = m_first / m_mentioned。
    #:
    #: 和上面三个不是一回事：那三个是「命中落在篇幅的哪一段」，
    #: 这个是「在被监测品牌里第几个出场」。**不是「AI 首推我们」**，
    #: 口径见 API.md §7.1。
    #:
    #: 之所以必须由后端给：rank 逐条挂在 MentionOut 上，前端要自己数就得
    #: 拉全量 responses —— 每行都拖着完整 full_text，为一个 KPI 拉整批全文。
    m_first: int = 0


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


class CitationDomainRow(BaseModel):
    domain: str
    #: 被引用的**次数**（口径：一条回答里引 3 次就计 3，用户 2026-08-22 拍板）
    n_citations: int
    #: **诊断字段，不参与排序。** 出现在几条不同样本里 ——
    #: 没有它，「4 次」和「4 条样本各引 1 次」在榜单上长得一模一样，
    #: 而聚合型站点很容易在单条回答里占掉一大半引用
    n_samples: int


class CitationDomainsOut(BaseModel):
    filters: Dict[str, Any]
    n_citations: int
    n_domains: int
    items: List[CitationDomainRow]
