from geo_metrics import (
    MentionMatch,
    aggregate_visibility,
    composite_score,
    share_of_voice,
    collapse_trials,
    Trial,
)
from geo_metrics.aggregate import ResponseObservation


def test_aggregate_and_score():
    rows = [
        ResponseObservation(
            MentionMatch(True, "body", "x", 0),
            1.0,
            True,
            0.5,
        ),
        ResponseObservation(
            MentionMatch(False, "none", None, None),
            0.0,
            False,
            0.0,
        ),
    ]
    agg = aggregate_visibility(rows)
    assert agg.sample_size == 2
    assert agg.visibility_rate == 0.5
    assert agg.recommend_rate == 0.5
    score = composite_score(agg)
    assert 0 <= score <= 100


def test_sov():
    assert share_of_voice(3, 1) == 0.75
    assert share_of_voice(0, 0) == 0.0


def test_sampling_collapse():
    c = collapse_trials(
        [
            Trial("yes"),
            Trial("no"),
            Trial("src"),
            Trial("error"),
        ]
    )
    assert c.measured == 3
    assert c.errors == 1
    assert abs(c.presence_rate - 2 / 3) < 1e-9
    assert c.representative in ("yes", "src", "no")
