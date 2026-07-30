from __future__ import annotations

from .config import DEFAULT_CONFIG, MetricsConfig
from .mention import match_brand


def is_recommended(
    body: str,
    aliases: list[str],
    *,
    position_rank: int | None = None,
    config: MetricsConfig = DEFAULT_CONFIG,
) -> bool:
    if position_rank == 1:
        return True
    text = body or ""
    for kw in config.recommend_keywords:
        start = 0
        while True:
            i = text.find(kw, start)
            if i < 0:
                break
            window = text[max(0, i - 40) : i + len(kw) + 40]
            if match_brand(window, aliases).mention_type == "body":
                return True
            start = i + len(kw)
    return False
