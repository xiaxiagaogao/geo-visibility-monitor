"""首位提及率的分子 —— counts 必须给出 ``m_first``（不依赖数据库）。

背景：``position_rank`` 从 v3 标注器起就落库了，但 ``/v1/counts`` 从来没暴露过
它的聚合值 —— 七个 m_* 字段里没有一个是「出场顺位第一的样本数」。
于是「首位提及率」这个 KPI 前端算不出来：rank 只逐条挂在 ``MentionOut`` 上，
要自己数就得拉全量 ``/v1/responses``，而那个接口没有 run_id 过滤、
且每行都拖着完整 ``full_text``（API.md §7 明确警告矩阵别全量拉）。

这组用例守的是**口径**：``m_first`` 是位置事实的计数，不是「AI 首推我们」，
且它必须是 ``m_mentioned`` 的子集 —— 前端拿它当分子、``m_mentioned`` 当分母。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.services.counts import _accumulate_mention, _empty_brand_counts


@dataclass
class FakeMention:
    """``_accumulate_mention`` 只读这四个属性，不必造 ORM 行。"""

    mentioned: bool = True
    mention_type: str = "body"
    position_bucket: Optional[str] = "head"
    position_rank: Optional[int] = None


def accumulate(*mentions: FakeMention) -> dict:
    bc = _empty_brand_counts(34)
    for m in mentions:
        _accumulate_mention(bc, m)
    return bc


def test_empty_counts_include_m_first():
    """字段必须存在且从 0 起 —— 缺键会让 _accumulate_mention 抛 KeyError。"""
    assert _empty_brand_counts(34)["m_first"] == 0


def test_rank_one_counts_toward_m_first():
    bc = accumulate(FakeMention(position_rank=1))
    assert bc["m_first"] == 1
    assert bc["m_mentioned"] == 1


def test_rank_two_and_beyond_do_not_count():
    bc = accumulate(
        FakeMention(position_rank=2),
        FakeMention(position_rank=3),
        FakeMention(position_rank=9),
    )
    assert bc["m_first"] == 0
    assert bc["m_mentioned"] == 3, "它们仍然是被提及了，只是不在第一位"


def test_citation_only_has_no_rank_and_does_not_count():
    """正文没出现 → rank 是 None，不是排最后（annotate 的口径，见 §7.1）。"""
    bc = accumulate(
        FakeMention(mention_type="citation_only", position_bucket=None, position_rank=None)
    )
    assert bc["m_first"] == 0
    assert bc["m_citation_only"] == 1


def test_not_mentioned_does_not_count():
    bc = accumulate(
        FakeMention(mentioned=False, mention_type="none", position_bucket=None, position_rank=None)
    )
    assert bc["m_first"] == 0
    assert bc["m_mentioned"] == 0


def test_m_first_never_exceeds_m_mentioned():
    """前端要拿 m_first / m_mentioned 当比率，分子大于分母就会出现 >100%。"""
    bc = accumulate(
        FakeMention(position_rank=1),
        FakeMention(position_rank=1),
        FakeMention(position_rank=4),
        FakeMention(mentioned=False, mention_type="none", position_bucket=None),
    )
    assert bc["m_first"] == 2
    assert bc["m_mentioned"] == 3
    assert bc["m_first"] <= bc["m_mentioned"]


def test_rank_zero_would_not_be_counted_as_first():
    """rank 是 1-based。写成 `if m.position_rank:` 看着等价，

    但那样将来若改成 0-based 会静默把第一名漏掉、把 0 当假值跳过。
    这条用例把「必须 == 1」钉死。
    """
    bc = accumulate(FakeMention(position_rank=0))
    assert bc["m_first"] == 0


def test_schema_exposes_m_first():
    """服务层数对了但 schema 没这个字段，Pydantic 会在序列化时丢掉它。"""
    from app.schemas.counts import BrandMentionCounts

    assert "m_first" in BrandMentionCounts.model_fields
    assert BrandMentionCounts(brand_id=34).m_first == 0
    assert BrandMentionCounts(**_empty_brand_counts(34)).m_first == 0
