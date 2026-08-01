"""offset 契约测试。

docs/03-metrics-spec.md §1.2 规定 position_bucket 基于「**首次**提及 offset」，
且 annotate.py 会拿这个 offset 直接去切**原文**做 evidence_snippet。
所以 match_brand 必须保证两件事：

1. 返回的是最早出现的那个别名，不是最长的那个
2. offset 可以直接索引传入的 body（不能是归一化后字符串的下标）
"""
from geo_metrics import match_brand, position_bucket


def test_offset_indexes_the_original_body():
    """曾经的 bug：_norm() 做了 strip()，offset 少算了前导空白的长度。"""
    body = "\n\n\n\n\n话题：我认为土巴兔是不错的装修平台。"
    m = match_brand(body, ["土巴兔"])
    assert m.offset == body.find("土巴兔")
    assert body[m.offset : m.offset + len(m.matched_term)] == "土巴兔"


def test_offset_survives_case_folding_length_change():
    """casefold() 会改长度（ß→ss），offset 不能因此错位。"""
    body = "Straße Brand X here"
    m = match_brand(body, ["brand x"])
    assert m.offset == body.find("Brand X")
    assert body[m.offset : m.offset + len(m.matched_term)].casefold() == "brand x"


def test_first_mention_wins_not_longest_alias():
    """曾经的 bug：按别名长度降序匹配，长别名在文末 → 位置被判成 tail。"""
    body = "耐克是首选。" + "无关内容。" * 60 + "另外 耐克运动鞋 也不错。"
    m = match_brand(body, ["耐克", "耐克运动鞋"])
    assert m.offset == 0
    assert position_bucket(body, m.offset) == "head"


def test_alias_order_does_not_change_result():
    body = "先提到 齐家网 ，后面才说 齐家 。"
    a = match_brand(body, ["齐家", "齐家网"])
    b = match_brand(body, ["齐家网", "齐家"])
    assert a.offset == b.offset == body.find("齐家网")
    # 同一位置起头时取更具体（更长）的那个词
    assert a.matched_term == b.matched_term == "齐家网"


def test_case_insensitive_body_match_keeps_offset():
    body = "我们推荐 TUBATU 这个平台。"
    m = match_brand(body, ["Tubatu"])
    assert m.mention_type == "body"
    assert m.offset == body.find("TUBATU")


def test_citation_only_has_no_offset():
    m = match_brand("今天天气不错", ["土巴兔"], citation_text="来源：土巴兔官网")
    assert m.mention_type == "citation_only"
    assert m.offset is None


def test_duplicate_aliases_are_harmless():
    m = match_brand("土巴兔很好", ["土巴兔", "土巴兔", " 土巴兔 "])
    assert m.offset == 0
