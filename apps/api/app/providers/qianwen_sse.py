"""千问 SSE 流的解析（P2-37）—— 抽引用 + 判有没有联网。**纯函数。**

## 为什么必须走流

**DOM 那条路是死的**（2026-08-17 节点实测，`PHASE2.md` §4.0.1 第五节）：
`[class*="search-content-"]` 那块只有 favicon 图，三种点击方式都展不开、外链 0 条；
favicon 反查出来的是**图标自己在 CDN 上的路径**，不是被引用的网页。

而引用**一直在流里，只是浏览器不渲染** —— 与 NDSS 2026 那篇论文的观察一致。
实测结构：

```text
端点   POST https://chat2.qianwen.com/api/v2/chat   （SSE）
帧     data:{...,"data":{"messages":[{...}]}}
引用   messages[].mime_type == "bar/progress"
       meta_data.match_num           ← 来源数（= 页面「N 篇来源」）
       meta_data.list[] 每条：title / url / raw_url / name / publish_time / summary
```

**公开圈没有任何项目从 `qianwen.com` 抽出过引用**，这份结构是本仓自测的。

## 只解析，不留存

与 DeepSeek / 豆包同一条纪律：**流的正文不落库**。这里在内存里解析完，
只把抽出来的引用交出去 —— `raw` 里留的是来源列表本身（站点名、发布时间这些
Citation 表里没有列的字段），不是整条流。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.providers.base import CitationData

logger = logging.getLogger("geo.qianwen_sse")

#: 带引用的那种帧
PROGRESS_MIME = "bar/progress"


@dataclass
class SearchTrace:
    """一次回答的「联网」痕迹。"""

    citations: List[CitationData] = field(default_factory=list)
    #: 来源数（= 页面上那个「N 篇来源」）。``None`` = 没抓到帧
    match_num: Optional[int] = None
    #: 来源列表原样留一份 —— 站点名与发布时间在 Citation 表里没有列，
    #: 而它们是实测多拿到的东西，丢掉等于把一次真机产出扔了
    raw: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def search_used(self) -> Optional[bool]:
        """**三态。** ``None`` 是「不知道」，不是「没联网」。

        混为一谈就是把「没记」说成「没联网」，而 `search_used` 要拿去分桶报告
        （`PHASE2.md` §4.0.1）—— 分错桶等于报告里多一条假结论。
        与 P2-36「探不到就留 NULL，不编默认值」同一条规矩。
        """
        if self.match_num is None:
            return None
        return self.match_num > 0


def parse_stream(body: Optional[str]) -> SearchTrace:
    """从 SSE 正文里抽引用与来源数。**绝不抛异常。**

    它跑在一条**已经拿到答案**的路径上 —— 抛出去等于用一条配额换一个失败，
    而答案本身是好的。流里混着心跳、``[DONE]``、半截 JSON 都是常态。
    """
    trace = SearchTrace()
    if not body:
        return trace

    seen_urls = set()
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload in ("[DONE]", "null"):
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        for msg in _messages(data):
            if msg.get("mime_type") != PROGRESS_MIME:
                continue
            meta = msg.get("meta_data") or {}
            num = meta.get("match_num")
            if isinstance(num, int):
                # 取最大的一个：SSE 是渐进下发的，后面的帧可能还没补齐
                trace.match_num = num if trace.match_num is None else max(trace.match_num, num)
            for item in meta.get("list") or []:
                _add(trace, item, seen_urls)
    return trace


def _messages(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    msgs = ((data.get("data") or {}).get("messages")) or []
    return [m for m in msgs if isinstance(m, dict)]


def _add(trace: SearchTrace, item: Any, seen: set) -> None:
    if not isinstance(item, dict):
        return
    # **`raw_url` 优先。** `url` 是跳转包装（s.qianwen.com/r?u=…），
    # 拿它算 domain 会让整张引用域名分布变成 s.qianwen.com —— 而
    # 「哪些站被引用」正是这份数据的分析价值所在
    url = (item.get("raw_url") or item.get("url") or "").strip()
    if not url or url in seen:
        return
    seen.add(url)
    trace.raw.append(item)
    trace.citations.append(
        CitationData(
            url=url,
            title=item.get("title") or None,
            snippet=item.get("summary") or None,
            domain=urlparse(url).netloc or None,
            cite_index=len(trace.citations) + 1,
        )
    )
