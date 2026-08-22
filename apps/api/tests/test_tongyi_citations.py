"""千问的引用提取与联网标注（P2-37）。**纯函数，本机可跑，不需要 playwright。**

## 结构从哪儿来

2026-08-17 在采集节点上实测拿到的（`PHASE2.md` §4.0.1 第五节）：

```text
端点   POST https://chat2.qianwen.com/api/v2/chat   （SSE）
帧     data:{...,"data":{"messages":[{...}]}}
引用   messages[].mime_type == "bar/progress"
       meta_data.match_num           ← 来源数（= 页面「N 篇来源」）
       meta_data.list[] 每条：title / url / raw_url / name（站点）/ publish_time / summary
```

**DOM 那条路是死的**（只有 favicon 图，外链 0 条；favicon 反查出来的是图标自己在
CDN 上的路径）。公开圈没有任何项目从 `qianwen.com` 抽出过引用 —— 这份结构是本仓自测的。

## 三态，不是两态

`search_used` 必须能表达**「不知道」**：

- ``True``  —— 流里有 `bar/progress` 帧且 `match_num > 0`
- ``False`` —— 有帧但 `match_num == 0`：**确认这次没联网**
- ``None``  —— 压根没抓到帧：解析失败 / 老数据 / 别的平台

**`None` 和 `False` 混为一谈就是把「没记」说成「没联网」**，而按 §4.0.1
的口径 `search_used` 要拿来分桶报告 —— 分错桶等于报告里多一条假结论。
这和 P2-36「探不到就留 NULL，不编默认值」是同一条规矩。
"""
from __future__ import annotations

import json

from app.providers.qianwen_sse import parse_stream


def _frame(messages):
    return "data:" + json.dumps({"data": {"messages": messages}}, ensure_ascii=False)


def _progress(match_num, items):
    return {
        "mime_type": "bar/progress",
        "meta_data": {"match_num": match_num, "list": items},
    }


ITEM = {
    "title": "2026 国产跑鞋横评",
    "url": "https://s.qianwen.com/r?u=abc",
    "raw_url": "https://www.runnersworld.cn/review/2026",
    "name": "跑者世界",
    "publish_time": "2026-07-11",
    "summary": "对比了安踏、李宁、特步的中底回弹……",
}


# ─────────────────────────────────────────────────────────── 抽引用


def test_extracts_a_citation_from_a_progress_frame():
    trace = parse_stream(_frame([_progress(1, [ITEM])]))

    assert len(trace.citations) == 1
    c = trace.citations[0]
    assert c.title == "2026 国产跑鞋横评"
    assert c.snippet.startswith("对比了安踏")
    assert c.cite_index == 1


def test_prefers_raw_url_over_the_wrapped_one():
    """`url` 是跳转包装（`s.qianwen.com/r?u=…`），`raw_url` 才是真正被引用的网页。

    **这一条直接决定 domain 对不对** —— 而 domain 是 GEO 分析里
    「哪些站被引用」的唯一依据。取错的话整张引用域名分布都是 `s.qianwen.com`。
    """
    trace = parse_stream(_frame([_progress(1, [ITEM])]))

    assert trace.citations[0].url == "https://www.runnersworld.cn/review/2026"
    assert trace.citations[0].domain == "www.runnersworld.cn"


def test_falls_back_to_url_when_raw_url_is_absent():
    item = {k: v for k, v in ITEM.items() if k != "raw_url"}
    trace = parse_stream(_frame([_progress(1, [item])]))

    assert trace.citations[0].url == "https://s.qianwen.com/r?u=abc"


def test_the_same_source_across_frames_is_not_counted_twice():
    """SSE 是渐进下发的 —— 同一批来源会在多帧里重复出现。

    不去重的话，一条回答会挂着十几条重复引用，
    而「被引用了几个站」是要拿去做分析的。
    """
    body = "\n".join([_frame([_progress(1, [ITEM])]), _frame([_progress(1, [ITEM])])])

    assert len(parse_stream(body).citations) == 1


def test_cite_index_is_assigned_in_order():
    second = dict(ITEM, raw_url="https://sports.example.cn/b", title="另一篇")
    trace = parse_stream(_frame([_progress(2, [ITEM, second])]))

    assert [c.cite_index for c in trace.citations] == [1, 2]


# ─────────────────────────────────────────────────── 联网标注（三态）


def test_sources_found_means_search_was_used():
    trace = parse_stream(_frame([_progress(7, [ITEM])]))

    assert trace.search_used is True
    assert trace.match_num == 7


def test_zero_sources_is_a_confirmed_no_not_an_unknown():
    """**这正是监测集的常态**：品牌对比类提问不触发联网（run 296 十条全 0）。

    §4.0.1 的拍板是「无搜索输出是结果，不是废样本」—— 所以这里必须是
    确定的 `False`，它要进报告的分桶。
    """
    trace = parse_stream(_frame([_progress(0, [])]))

    assert trace.search_used is False
    assert trace.match_num == 0


def test_no_progress_frame_at_all_is_unknown_not_false():
    """**`None` ≠ `False`。** 没抓到帧是「我们不知道」，
    说成「没联网」就是在报告里凭空造一条结论。"""
    trace = parse_stream(_frame([{"mime_type": "text/plain", "content": "答案正文"}]))

    assert trace.search_used is None
    assert trace.citations == []


def test_an_empty_body_is_unknown():
    assert parse_stream("").search_used is None
    assert parse_stream(None).search_used is None


# ─────────────────────────────────────────────────────────── 健壮性


def test_garbage_lines_are_skipped_not_fatal():
    """流里混着心跳、`[DONE]`、半截 JSON 是常态。**解析器不能成为故障源** ——
    它跑在一条已经拿到答案的路径上，抛异常等于用一次配额换一个 500。"""
    body = "\n".join([
        ": heartbeat",
        "data:[DONE]",
        "data:{半截的",
        "",
        _frame([_progress(3, [ITEM])]),
        "data:null",
    ])

    trace = parse_stream(body)
    assert trace.search_used is True and len(trace.citations) == 1


def test_items_missing_a_url_are_dropped():
    """没有 URL 的引用没有分析价值，而 `domain` 是 NOT NULL 的。"""
    trace = parse_stream(_frame([_progress(2, [{"title": "无链接"}, ITEM])]))

    assert len(trace.citations) == 1


def test_the_extra_fields_are_kept_for_later():
    """站点名与发布时间**在 Citation 表里没有列**，但它们是实测多拿到的东西。

    丢掉等于把一次真机实测的产出扔了 —— 原样留在 `raw` 里跟着 `raw_json` 落库。
    """
    trace = parse_stream(_frame([_progress(1, [ITEM])]))

    assert trace.raw[0]["name"] == "跑者世界"
    assert trace.raw[0]["publish_time"] == "2026-07-11"
