"""stream 与 DOM 之间怎么选 L0 正文。

用例取自 VPS 实测（job 37 / response 22，2026-08-01）：

    DOM    挑选一家靠谱的装修公司是件耗时又重要的事，…
    stream FINISHEDSEARCH一家靠谱的装修公司是件耗时又重要的事，…

SSE 拼接丢了首块「挑选」，位置被 FINISHEDSEARCH 顶替。
原实现「谁长选谁」，带胶水的 stream 反而更长 → 每次都选中缺头那份。
首字直接决定 position_bucket 的 head/middle/tail。
"""
from __future__ import annotations

from app.providers.deepseek_web import _pick_answer_text

REAL_DOM = (
    "挑选一家靠谱的装修公司是件耗时又重要的事，“哪家好”的答案会因你所在的城市和"
    "具体需求而大不相同。综合2026年的行业信息看，经验更丰富、报价更透明的品牌，"
    "在各地都更受认可。"
)
REAL_STREAM = "FINISHEDSEARCH" + REAL_DOM[len("挑选") :]


def test_real_capture_prefers_dom():
    assert _pick_answer_text(REAL_STREAM, REAL_DOM) == REAL_DOM
    assert _pick_answer_text(REAL_STREAM, REAL_DOM).startswith("挑选")


def test_glue_prefixed_stream_loses_even_when_longer():
    dom = "挑选一家靠谱的装修公司。" * 4
    stream = "FINISHEDSEARCH" + dom + "多出来的一大段尾巴" * 5
    assert _pick_answer_text(stream, dom) == dom


def test_dom_wins_when_essentially_complete():
    """DOM 是渲染后的真值，长度相当时优先它。"""
    dom = "这是一段完整的回答正文，足够长可以通过噪声判定，内容也具备段落结构。" * 2
    stream = dom + "尾"
    assert _pick_answer_text(stream, dom) == dom


def test_stream_wins_when_dom_is_far_shorter():
    """DOM 还没渲染完时（生成中），仍然可以退回 stream。"""
    dom = "这是一段刚开始渲染的回答，长度还不够。" * 2
    stream = dom + "后面还有很多很多内容需要继续补充说明，篇幅明显更长。" * 6
    assert _pick_answer_text(stream, dom) == stream


def test_noisy_dom_never_wins():
    """侧栏误抓不能顶替正文。"""
    noise = "开启新对话\n" * 20 + "2026装修公司推荐\n" * 5
    stream = "这是一段真正的回答正文，足够长可以通过噪声判定，内容也具备段落结构。" * 2
    assert _pick_answer_text(stream, noise) == stream


def test_empty_sides():
    assert _pick_answer_text("", "只有 DOM") == "只有 DOM"
    assert _pick_answer_text("只有 stream", "") == "只有 stream"
    assert _pick_answer_text("", "") == ""
