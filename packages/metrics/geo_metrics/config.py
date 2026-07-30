from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MetricsConfig:
    presence_include_citation_only: bool = True
    position_scores: dict[str, float] = field(
        default_factory=lambda: {"head": 1.0, "middle": 0.6, "tail": 0.3, "none": 0.0}
    )
    visibility_weights: dict[str, float] = field(
        default_factory=lambda: {"mention": 0.4, "position": 0.3, "sentiment": 0.3}
    )
    recommend_keywords: tuple[str, ...] = (
        "推荐",
        "首选",
        "建议选择",
        "建议使用",
        "强烈推荐",
        "优先考虑",
    )
    positive_words: tuple[str, ...] = (
        "优秀",
        "好用",
        "可靠",
        "领先",
        "专业",
        "推荐",
        "满意",
        "高质量",
        "靠谱",
        "出色",
    )
    negative_words: tuple[str, ...] = (
        "差",
        "糟糕",
        "不推荐",
        "坑",
        "投诉",
        "虚假",
        "劣质",
        "失望",
        "翻车",
        "避雷",
    )


DEFAULT_CONFIG = MetricsConfig()
