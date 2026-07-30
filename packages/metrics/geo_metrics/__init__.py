"""GEO metrics: mention, position, sentiment, aggregation."""

from .config import MetricsConfig, DEFAULT_CONFIG
from .mention import match_brand, MentionMatch
from .position import position_bucket, position_score
from .sentiment import score_sentiment
from .recommend import is_recommended
from .aggregate import (
    aggregate_visibility,
    composite_score,
    share_of_voice,
    AggregateResult,
)
from .sampling import collapse_trials, Trial, PresenceCollapse

__all__ = [
    "MetricsConfig",
    "DEFAULT_CONFIG",
    "match_brand",
    "MentionMatch",
    "position_bucket",
    "position_score",
    "score_sentiment",
    "is_recommended",
    "aggregate_visibility",
    "composite_score",
    "share_of_voice",
    "AggregateResult",
    "collapse_trials",
    "Trial",
    "PresenceCollapse",
]
