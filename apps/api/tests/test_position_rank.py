"""出场顺位（position_rank）的口径（不依赖数据库）。

背景：``position_rank`` 这一列从 B4 起就存在，但 annotate 每次都硬写 None ——
``match_brand`` 明明算出了 offset，切完 evidence_snippet 就丢掉了。

这组用例守的是**口径**，不是实现：rank 是「正文里谁先出现」的位置事实，
不是「AI 推荐的第一名」。两者一旦混淆，UI 上就会把「第一个被提到」
说成「首推」，那是拿措辞夸大结论。
"""
from __future__ import annotations

from geo_metrics import match_brand
from geo_metrics.mention import MentionMatch

from app.services.annotate import assign_position_ranks, surface_term


def body(offset: int, term: str = "x") -> MentionMatch:
    return MentionMatch(True, "body", term, offset)


CITED = MentionMatch(True, "citation_only", "x", None)
MISSING = MentionMatch(False, "none", None, None)


def test_ranks_follow_first_offset_not_input_order():
    """入参顺序是 brand_id 顺序，排名必须由 offset 决定。"""
    ranks = assign_position_ranks([(10, body(300)), (11, body(5)), (12, body(120))])
    assert ranks == {11: 1, 12: 2, 10: 3}


def test_citation_only_has_no_rank_not_last_place():
    """引用里命中 = 正文根本没出现，没有「出场位置」—— 是 None，不是排最后。"""
    ranks = assign_position_ranks([(10, body(50)), (11, CITED), (12, body(90))])
    assert ranks == {10: 1, 12: 2}
    assert 11 not in ranks


def test_missing_brands_have_no_rank():
    ranks = assign_position_ranks([(10, body(0)), (11, MISSING)])
    assert ranks == {10: 1}


def test_offset_zero_is_rank_one_not_falsy_skipped():
    """offset=0 是正文第一个字 —— 最容易被 `if offset:` 写漏的边界。"""
    ranks = assign_position_ranks([(10, body(0)), (11, body(1))])
    assert ranks[10] == 1
    assert ranks[11] == 2


def test_same_offset_is_deterministic():
    """别名重叠可能撞同一个 offset；同样输入必须永远同样输出。"""
    a = assign_position_ranks([(20, body(7)), (10, body(7))])
    b = assign_position_ranks([(10, body(7)), (20, body(7))])
    assert a == b == {10: 1, 20: 2}


def test_no_body_hits_yields_empty_mapping():
    assert assign_position_ranks([(10, CITED), (11, MISSING)]) == {}
    assert assign_position_ranks([]) == {}


def test_matched_term_keeps_original_casing():
    """match_brand 给的是折叠后的 'nike'，落库要存原文里的 'Nike'。

    否则「别名命中」展示出来和原文不一致，且下面那条不变量不成立。
    """
    text = "国际品牌里 Nike 和 adidas 依然强势。"
    m = match_brand(text, ["耐克", "Nike", "NIKE"])
    assert m.matched_term == "nike", "前提：match_brand 返回的是折叠形式"
    assert surface_term(text, m) == "Nike"


def test_offset_and_term_slice_the_original_text():
    """不变量：full_text[first_offset : +len(matched_term)] == matched_term。

    前端靠它自检高亮有没有错位；折叠若不是长度守恒，这条会立刻炸。
    """
    text = "除了安踏、李宁，ANTA 的跑鞋也不错。"
    for aliases in (["安踏", "ANTA"], ["李宁"]):
        m = match_brand(text, aliases)
        term = surface_term(text, m)
        assert text[m.offset : m.offset + len(term)] == term


def test_citation_only_term_survives_without_offset():
    """引用命中没有正文 offset，仍要保留命中的词，不能变成 None。"""
    m = MentionMatch(True, "citation_only", "erke", None)
    assert surface_term("正文里没有它", m) == "erke"


def test_surface_term_is_none_when_nothing_matched():
    assert surface_term("随便一段文字", MISSING) is None


def test_rank_is_dense_within_monitored_set():
    """名次在**被监测品牌集合内**连续。

    回答里可能先提了我们没监测的品牌，我们照样从 1 开始 ——
    含义是「我们关心的品牌里它最先出现」，不是「全文第一个品牌」。
    这条口径必须写进文档，否则 rank=1 会被读成「AI 首推我们」。
    """
    ranks = assign_position_ranks([(10, body(900)), (11, body(950))])
    assert sorted(ranks.values()) == [1, 2]
