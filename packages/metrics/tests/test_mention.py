from geo_metrics import match_brand


def test_body_match_chinese():
    m = match_brand("我认为土巴兔是不错的装修平台", ["土巴兔", "Tubatu"])
    assert m.mentioned and m.mention_type == "body"
    assert m.matched_term == "土巴兔"
    assert m.offset is not None


def test_citation_only():
    m = match_brand(
        "今天天气不错",
        ["土巴兔"],
        citation_text="来源：土巴兔官网经验文章",
    )
    assert m.mentioned and m.mention_type == "citation_only"


def test_none():
    m = match_brand("没有相关品牌", ["土巴兔"])
    assert not m.mentioned and m.mention_type == "none"
