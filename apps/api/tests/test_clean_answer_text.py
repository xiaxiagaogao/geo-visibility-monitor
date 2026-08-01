"""_clean_answer_text 不得吃掉正文。

这些用例全部来自 review 时对旧实现的实测：旧版会把正常答案改写或截断，
而且改写结果直接进了 full_text（L0），原文无法追回。
"""
from __future__ import annotations

import pytest

from app.providers.deepseek_web import _clean_answer_text


@pytest.mark.parametrize(
    "text",
    [
        # 旧实现：^6年 → 2026年，把模型说的「6年内」改成「2026年内」
        "6年内这个品牌增长很快，建议关注。",
        # 旧实现：开头 SEARCH 无边界条件，砍成「引擎优化…」
        "SEARCH引擎优化是一个长期工作，需要持续投入内容建设。",
        # 旧实现：结尾 (SEARCH)[\w一-鿿]*$ 把后面整串吞掉
        "该公司成立于2010年，目前主营业务为家装SEARCH",
        # 正常中文答案不该被动
        "推荐土巴兔，其次是齐家网。整体来看差异不大，可以按预算选择。",
        "researching 这个词开头也不该被剥",
        # 歧义：分不清是胶水还是正文（旧实现正是在这里猜 2026 猜错的）。
        # 宁可原样留在 L0 里，也不改写模型答案。
        "FINISHEDSEARCH2026年的装修市场…",
    ],
)
def test_leaves_real_content_untouched(text):
    assert _clean_answer_text(text) == text


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("FINISHEDSEARCH 综合来看，土巴兔口碑不错。", "综合来看，土巴兔口碑不错。"),
        ("FINISHED: 答案正文在这里。", "答案正文在这里。"),
        ("SEARCH|土巴兔是装修平台。", "土巴兔是装修平台。"),
        ("SEARCH 引擎优化需要时间。", "引擎优化需要时间。"),
    ],
)
def test_strips_standalone_glue_token(raw, expected):
    assert _clean_answer_text(raw) == expected


def test_empty_input():
    assert _clean_answer_text("") == ""
    assert _clean_answer_text(None) == ""
