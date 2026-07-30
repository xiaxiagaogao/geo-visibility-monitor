from __future__ import annotations

from dataclasses import dataclass

from .config import DEFAULT_CONFIG, MetricsConfig
from .mention import MentionMatch


@dataclass(frozen=True)
class ResponseObservation:
    mention: MentionMatch
    position_score: float
    recommended: bool
    sentiment_score: float


@dataclass(frozen=True)
class AggregateResult:
    sample_size: int
    visibility_rate: float
    recommend_rate: float
    avg_position_score: float
    sentiment_net: float


def _is_hit(m: MentionMatch, config: MetricsConfig) -> bool:
    if m.mention_type == "body":
        return True
    if m.mention_type == "citation_only" and config.presence_include_citation_only:
        return True
    return False


def aggregate_visibility(
    rows: list[ResponseObservation],
    config: MetricsConfig = DEFAULT_CONFIG,
) -> AggregateResult:
    n = len(rows)
    if n == 0:
        return AggregateResult(0, 0.0, 0.0, 0.0, 0.0)
    hits = sum(1 for r in rows if _is_hit(r.mention, config))
    rec = sum(1 for r in rows if r.recommended)
    pos = sum(r.position_score for r in rows) / n
    sent = sum(r.sentiment_score for r in rows) / n
    return AggregateResult(
        sample_size=n,
        visibility_rate=hits / n,
        recommend_rate=rec / n,
        avg_position_score=pos,
        sentiment_net=sent,
    )


def composite_score(
    agg: AggregateResult,
    config: MetricsConfig = DEFAULT_CONFIG,
) -> float:
    w = config.visibility_weights
    sentiment01 = (agg.sentiment_net + 1.0) / 2.0
    s = (
        w.get("mention", 0.4) * agg.visibility_rate
        + w.get("position", 0.3) * agg.avg_position_score
        + w.get("sentiment", 0.3) * sentiment01
    )
    return round(100.0 * s, 2)


def share_of_voice(brand_hits: int, competitor_hits: int) -> float:
    denom = brand_hits + competitor_hits
    if denom <= 0:
        return 0.0
    return brand_hits / denom
