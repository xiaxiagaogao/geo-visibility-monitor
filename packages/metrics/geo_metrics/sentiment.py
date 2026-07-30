from __future__ import annotations

from dataclasses import dataclass

from .config import DEFAULT_CONFIG, MetricsConfig


@dataclass(frozen=True)
class SentimentResult:
    label: str  # positive | neutral | negative
    score: float  # ~[-1, 1]


def score_sentiment(
    text: str,
    config: MetricsConfig = DEFAULT_CONFIG,
) -> SentimentResult:
    t = text or ""
    pos = sum(1 for w in config.positive_words if w in t)
    neg = sum(1 for w in config.negative_words if w in t)
    if pos == 0 and neg == 0:
        return SentimentResult("neutral", 0.0)
    raw = (pos - neg) / (pos + neg)
    if raw > 0.15:
        label = "positive"
    elif raw < -0.15:
        label = "negative"
    else:
        label = "neutral"
    return SentimentResult(label, raw)
