from __future__ import annotations

from .config import DEFAULT_CONFIG, MetricsConfig


def position_bucket(body: str, offset: int | None) -> str | None:
    if offset is None:
        return None
    n = max(len(body or ""), 1)
    if offset < n / 3:
        return "head"
    if offset < 2 * n / 3:
        return "middle"
    return "tail"


def position_score(
    bucket: str | None,
    config: MetricsConfig = DEFAULT_CONFIG,
) -> float:
    key = bucket or "none"
    return float(config.position_scores.get(key, 0.0))
