"""Unit tests for the CEP (complex event processing) detector.

Strictly offline — all data is constructed in-memory, no network or DB.
"""

from cep.automaton import EventAutomaton, Transition
from cep.cep_detector import CEPDetector
from cep.events import (
    PRICE_JUMP_DOWN,
    PRICE_JUMP_UP,
    SENTIMENT_DROP,
    SENTIMENT_SPIKE,
    VOLUME_SURGE,
    EventDetector,
    EventThresholds,
)
from ml.ensemble import EnsembleDetector


def _window(**overrides) -> dict:
    base = {
        "ticker": "AAPL",
        "price_change_rate": 0.001,
        "total_volume": 1000.0,
        "avg_sentiment": 0.0,
        "sentiment_shift": 0.0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# EventDetector — primitive events
# ---------------------------------------------------------------------------


def test_price_jump_up_and_down():
    d = EventDetector()
    assert d.detect(_window(price_change_rate=0.05)) == {PRICE_JUMP_UP}
    assert d.detect(_window(price_change_rate=-0.05)) == {PRICE_JUMP_DOWN}


def test_no_price_jump_below_threshold():
    d = EventDetector()
    assert d.detect(_window(price_change_rate=0.01)) == set()


def test_volume_surge_needs_warmup_then_fires():
    d = EventDetector()
    surge = _window(total_volume=6000.0)
    # Cold: no baseline yet -> cannot fire.
    assert VOLUME_SURGE not in d.detect(surge)
    for _ in range(5):
        d.update(_window(total_volume=1000.0))
    # 6000 / ~1000 baseline = 6x >= 3x ratio -> fires.
    assert VOLUME_SURGE in d.detect(surge)


def test_sentiment_drop_via_shift_and_floor_and_spike():
    d = EventDetector()
    assert SENTIMENT_DROP in d.detect(_window(sentiment_shift=-0.4))
    assert SENTIMENT_DROP in d.detect(_window(avg_sentiment=-0.6))
    assert SENTIMENT_SPIKE in d.detect(_window(sentiment_shift=0.4))


def test_update_advances_volume_baseline():
    d = EventDetector()
    d.update(_window(ticker="TSLA", total_volume=500.0))
    assert "TSLA" in d._vol_mean
    assert d._vol_obs["TSLA"] == 1


def test_custom_thresholds_respected():
    d = EventDetector(EventThresholds(price_jump=0.10))
    assert d.detect(_window(price_change_rate=0.05)) == set()
    assert d.detect(_window(price_change_rate=0.12)) == {PRICE_JUMP_UP}


# ---------------------------------------------------------------------------
# EventAutomaton — sequence recognition
# ---------------------------------------------------------------------------


def _ab_automaton(max_gap=2):
    return EventAutomaton(
        "ab",
        [Transition(0, "A", 1), Transition(1, "B", 2)],
        accept_state=2,
        severity=0.9,
        max_gap=max_gap,
    )


def test_sequential_match_within_gap_fires():
    a = _ab_automaton(max_gap=2)
    assert a.step("k", {"A"}) == 0.0  # 0 -> 1
    assert a.step("k", set()) == 0.0  # idle, age = 1 (< gap)
    assert a.step("k", {"B"}) == 0.9  # 1 -> 2 accept


def test_match_resets_after_gap_exceeded():
    a = _ab_automaton(max_gap=1)
    a.step("k", {"A"})  # 0 -> 1
    a.step("k", set())  # age = 1
    # Next window: partial match has expired, B from start state goes nowhere.
    assert a.step("k", {"B"}) == 0.0


def test_simultaneous_events_multi_hop_in_one_window():
    a = EventAutomaton(
        "abc",
        [Transition(0, "A", 1), Transition(1, "B", 2), Transition(2, "C", 3)],
        accept_state=3,
        severity=1.0,
        max_gap=3,
    )
    assert a.step("k", {"A", "B", "C"}) == 1.0


def test_per_ticker_isolation():
    a = _ab_automaton(max_gap=3)
    a.step("k1", {"A"})  # k1 -> state 1
    assert a.step("k2", {"B"}) == 0.0  # k2 is fresh; B from start goes nowhere
    assert a.step("k1", {"B"}) == 0.9  # k1 completes independently


# ---------------------------------------------------------------------------
# CEPDetector — scoring
# ---------------------------------------------------------------------------


def test_normal_window_scores_zero():
    d = CEPDetector()
    assert d.score(_window()) == 0.0


def test_lone_primitive_fires_point_layer():
    d = CEPDetector()
    score = d.score(_window(price_change_rate=0.05))
    assert score == -d._point_severity
    assert d.last_match("AAPL").startswith("point:")


def test_automata_only_ignores_lone_primitive():
    d = CEPDetector(point_severity=0.0)
    assert d.score(_window(price_change_rate=0.05)) == 0.0  # 0 -> 1, no accept, no point


def test_volume_led_breakout_sequence():
    d = CEPDetector()
    for _ in range(5):
        d.update(_window(total_volume=1000.0))
    d.score(_window(total_volume=6000.0))  # volume surge -> breakout state 1
    d.update(_window(total_volume=6000.0))
    score = d.score(_window(price_change_rate=0.05))  # price jump completes breakout
    assert score == -0.85
    assert d.last_match("AAPL") == "volume_led_breakout"


def test_flash_reversal_sequence():
    d = CEPDetector()
    d.score(_window(price_change_rate=0.05))  # up -> state 1
    score = d.score(_window(price_change_rate=-0.05))  # down -> reversal accept
    assert score == -0.80
    assert d.last_match("AAPL") == "flash_reversal"


def test_score_within_bounds():
    d = CEPDetector()
    for feats in (
        _window(),
        _window(price_change_rate=0.05),
        _window(sentiment_shift=-0.6),
        _window(price_change_rate=-0.9),
    ):
        score = d.score(feats)
        assert -1.0 <= score <= 0.0


def test_plugs_into_ensemble_and_flags_anomaly():
    cep = CEPDetector()
    ensemble = EnsembleDetector([cep], weights=[1.0], threshold=-0.5)
    score, per = ensemble.score(_window(price_change_rate=0.05))
    assert per == {"cep": score}
    assert ensemble.is_anomaly(score)  # -0.55 < -0.5
    assert not ensemble.is_anomaly(0.0)
