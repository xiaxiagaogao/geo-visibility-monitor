from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MentionLabel = Literal["yes", "src", "no", "error"]


@dataclass(frozen=True)
class Trial:
    mention: MentionLabel


@dataclass(frozen=True)
class PresenceCollapse:
    representative: Literal["yes", "src", "no"]
    presence_rate: float
    measured: int
    errors: int


def collapse_trials(trials: list[Trial]) -> PresenceCollapse:
    """Collapse multi-sample trials (aeo-platform style).

    - error excluded from denominator
    - hit = yes | src
    - representative: mode with tie-break yes > src > no
    """
    measured = [t for t in trials if t.mention != "error"]
    errors = len(trials) - len(measured)
    if not measured:
        return PresenceCollapse("no", 0.0, 0, errors)

    hits = sum(1 for t in measured if t.mention in ("yes", "src"))
    counts = {"yes": 0, "src": 0, "no": 0}
    for t in measured:
        if t.mention in counts:
            counts[t.mention] += 1

    # tie-break order
    order = ("yes", "src", "no")
    best = max(order, key=lambda k: (counts[k], -order.index(k)))
    return PresenceCollapse(
        representative=best,  # type: ignore[arg-type]
        presence_rate=hits / len(measured),
        measured=len(measured),
        errors=errors,
    )
