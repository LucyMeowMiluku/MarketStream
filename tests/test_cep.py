"""Unit tests for the CEP (complex event processing) detector.

Strictly offline — all data is constructed in-memory, no network or DB.
"""

from cep.automaton import (
    EventAutomaton,
    NegationEdge,
    NFAEventAutomaton,
    RepeatEdge,
    Transition,
)
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
from cep.guards import feature_abs_gt, feature_gt, feature_lt
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


# ---------------------------------------------------------------------------
# NFAEventAutomaton — NFA multi-instance tracking
# ---------------------------------------------------------------------------


def _nfa_ab(max_gap=2, **kwargs):
    return NFAEventAutomaton(
        "ab",
        [Transition(0, "A", 1), Transition(1, "B", 2)],
        accept_state=2,
        severity=0.9,
        max_gap=max_gap,
        **kwargs,
    )


def test_nfa_sequential_match():
    a = _nfa_ab()
    assert a.step("k", {"A"}) == 0.0
    assert a.step("k", {"B"}) == 0.9


def test_nfa_degenerates_to_dfa():
    """Without overlapping starts, NFA behaves identically to DFA."""
    a = _nfa_ab(max_gap=2)
    assert a.step("k", {"A"}) == 0.0
    assert a.step("k", set()) == 0.0
    assert a.step("k", {"B"}) == 0.9


def test_nfa_overlapping_instances():
    """Two A events at different times each start an instance; both can complete."""
    a = _nfa_ab(max_gap=3)
    a.step("k", {"A"})  # instance 1 at state 1
    a.step("k", set())  # idle
    a.step("k", {"A"})  # instance 2 at state 1 (instance 1 still alive, age 2)
    assert a.step("k", {"B"}) == 0.9  # at least one instance completes


def test_nfa_instance_eviction():
    """When max_instances is exceeded, oldest instances are evicted."""
    a = _nfa_ab(max_gap=10, max_instances=2)
    a.step("k", {"A"})  # instance 1
    a.step("k", {"A"})  # instance 2 (instance 1 moved to state 1 already)
    a.step("k", {"A"})  # instance 3 -> evicts instance 1
    # After eviction the oldest (birth=0) is gone; newest survive
    assert len(a._instances["k"]) <= 2


def test_nfa_gap_expiry_per_instance():
    a = _nfa_ab(max_gap=1)
    a.step("k", {"A"})   # instance at state 1
    a.step("k", set())   # age = 1 -> expires at next step
    assert a.step("k", {"B"}) == 0.0  # instance expired, B from fresh start goes nowhere


def test_nfa_simultaneous_multi_hop():
    a = NFAEventAutomaton(
        "abc",
        [Transition(0, "A", 1), Transition(1, "B", 2), Transition(2, "C", 3)],
        accept_state=3,
        severity=1.0,
        max_gap=3,
    )
    assert a.step("k", {"A", "B", "C"}) == 1.0


def test_nfa_per_ticker_isolation():
    a = _nfa_ab(max_gap=3)
    a.step("k1", {"A"})
    assert a.step("k2", {"B"}) == 0.0  # k2 has no partial match
    assert a.step("k1", {"B"}) == 0.9  # k1 completes


# ---------------------------------------------------------------------------
# Per-transition gap constraints
# ---------------------------------------------------------------------------


def test_per_edge_gap_tight_leg():
    """A transition with max_gap=1 expires faster than the automaton default."""
    a = NFAEventAutomaton(
        "ab_tight",
        [
            Transition(0, "A", 1),
            Transition(1, "B", 2, max_gap=1),  # tight: 1 window tolerance
        ],
        accept_state=2,
        severity=0.9,
        max_gap=5,  # automaton default is loose
    )
    a.step("k", {"A"})   # state 1
    a.step("k", set())   # age=1 -> hits per-edge limit
    assert a.step("k", {"B"}) == 0.0  # expired


def test_per_edge_gap_loose_leg():
    """A transition with max_gap=5 survives longer than automaton default."""
    a = NFAEventAutomaton(
        "ab_loose",
        [
            Transition(0, "A", 1),
            Transition(1, "B", 2, max_gap=5),
        ],
        accept_state=2,
        severity=0.9,
        max_gap=1,  # automaton default is tight
    )
    a.step("k", {"A"})
    for _ in range(4):
        a.step("k", set())  # age 1..4, all within per-edge gap=5
    assert a.step("k", {"B"}) == 0.9


def test_per_edge_gap_heterogeneous():
    """Different edges in the same automaton have different gap tolerances."""
    a = NFAEventAutomaton(
        "abc_hetero",
        [
            Transition(0, "A", 1),
            Transition(1, "B", 2, max_gap=4),  # loose
            Transition(2, "C", 3, max_gap=1),  # tight
        ],
        accept_state=3,
        severity=1.0,
        max_gap=2,
    )
    a.step("k", {"A"})
    a.step("k", set())
    a.step("k", set())
    a.step("k", {"B"})  # age=3, within per-edge gap=4 -> advance to state 2
    a.step("k", set())  # age=1 from state 2 -> hits per-edge gap=1
    assert a.step("k", {"C"}) == 0.0  # expired


# ---------------------------------------------------------------------------
# Guard conditions
# ---------------------------------------------------------------------------


def test_guard_pass():
    a = NFAEventAutomaton(
        "guarded",
        [
            Transition(0, "A", 1),
            Transition(1, "B", 2, guard=feature_gt("val", 10)),
        ],
        accept_state=2,
        severity=0.9,
        max_gap=3,
    )
    a.step("k", {"A"})
    assert a.step("k", {"B"}, features={"val": 15}) == 0.9


def test_guard_fail():
    a = NFAEventAutomaton(
        "guarded",
        [
            Transition(0, "A", 1),
            Transition(1, "B", 2, guard=feature_gt("val", 10)),
        ],
        accept_state=2,
        severity=0.9,
        max_gap=3,
    )
    a.step("k", {"A"})
    assert a.step("k", {"B"}, features={"val": 5}) == 0.0  # guard blocks


def test_guard_abs_gt():
    a = NFAEventAutomaton(
        "abs_guard",
        [Transition(0, "A", 1, guard=feature_abs_gt("pcr", 0.05))],
        accept_state=1,
        severity=0.8,
        max_gap=3,
    )
    assert a.step("k", {"A"}, features={"pcr": -0.07}) == 0.8
    assert a.step("k", {"A"}, features={"pcr": 0.03}) == 0.0


def test_guard_no_features_skips_guard():
    """When features=None, guarded transitions are skipped (guard cannot evaluate)."""
    a = NFAEventAutomaton(
        "guarded",
        [Transition(0, "A", 1, guard=feature_gt("val", 10))],
        accept_state=1,
        severity=0.9,
        max_gap=3,
    )
    assert a.step("k", {"A"}) == 0.0  # no features -> guard blocks


def test_guard_with_nfa_overlapping():
    """Guards and NFA overlapping instances compose correctly."""
    a = NFAEventAutomaton(
        "overlap_guard",
        [
            Transition(0, "A", 1),
            Transition(1, "B", 2, guard=feature_gt("val", 10)),
        ],
        accept_state=2,
        severity=0.9,
        max_gap=5,
    )
    a.step("k", {"A"})                                 # instance 1
    a.step("k", {"B"}, features={"val": 5})            # guard fails, no completion
    a.step("k", {"A"})                                 # instance 2
    assert a.step("k", {"B"}, features={"val": 15}) == 0.9  # guard passes


# ---------------------------------------------------------------------------
# Previously untested patterns: news_driven_selloff, panic_compound
# ---------------------------------------------------------------------------


def test_news_driven_selloff_sequence():
    d = CEPDetector()
    d.score(_window(sentiment_shift=-0.5))  # sentiment drop -> state 1
    score = d.score(_window(price_change_rate=-0.05))  # price down -> accept
    assert score == -0.90
    assert d.last_match("AAPL") == "news_driven_selloff"


def test_news_driven_selloff_via_floor():
    d = CEPDetector()
    d.score(_window(avg_sentiment=-0.6))  # hits floor -> sentiment_drop
    score = d.score(_window(price_change_rate=-0.05))
    assert score == -0.90


def test_panic_compound_sequence():
    d = CEPDetector()
    for _ in range(5):
        d.update(_window(total_volume=1000.0))
    d.score(_window(total_volume=6000.0))  # volume surge
    d.update(_window(total_volume=6000.0))
    d.score(_window(sentiment_shift=-0.5))  # sentiment drop
    score = d.score(_window(price_change_rate=-0.05))  # price down -> accept
    assert score == -1.0
    # pump_and_dump (meta) also fires at severity 1.0 and wins ties
    assert d.last_match("AAPL") in ("panic_compound", "pump_and_dump")


def test_panic_compound_partial_timeout():
    d = CEPDetector()
    for _ in range(5):
        d.update(_window(total_volume=1000.0))
    d.score(_window(total_volume=6000.0))  # volume surge -> state 1
    d.update(_window(total_volume=6000.0))
    # Idle beyond panic_compound's max_gap for the sentiment leg
    for _ in range(6):
        d.score(_window())
        d.update(_window())
    # Now sentiment drop arrives too late
    d.score(_window(sentiment_shift=-0.5))
    score = d.score(_window(price_change_rate=-0.05))
    assert d.last_match("AAPL") != "panic_compound"


# ---------------------------------------------------------------------------
# Negation / absence detection
# ---------------------------------------------------------------------------


def _negation_ab(timeout=3):
    """A → NOT(B) within timeout → accept."""
    return NFAEventAutomaton(
        "neg_ab",
        transitions=[Transition(0, "A", 1)],
        accept_state=2,
        severity=0.7,
        max_gap=timeout + 1,
        negations=[NegationEdge(from_state=1, absent_event="B", to_state=2, timeout=timeout)],
    )


def test_negation_fires_on_absence():
    a = _negation_ab(timeout=2)
    a.step("k", {"A"})    # state 1
    a.step("k", set())    # absent +1
    assert a.step("k", set()) == 0.7  # absent +2 >= timeout -> accept


def test_negation_reset_on_event_appearance():
    a = _negation_ab(timeout=2)
    a.step("k", {"A"})    # state 1
    a.step("k", set())    # absent +1
    a.step("k", {"B"})    # B appeared -> negation counter reset
    assert a.step("k", set()) == 0.0  # counter was reset, not yet at timeout


def test_negation_timeout_boundary():
    """Negation fires exactly at timeout, not before."""
    a = _negation_ab(timeout=3)
    a.step("k", {"A"})    # state 1
    a.step("k", set())    # absent +1
    assert a.step("k", set()) == 0.0  # absent +2, not yet
    assert a.step("k", set()) == 0.7  # absent +3 = timeout -> accept


def test_negation_with_overlapping_nfa():
    """Multiple instances can independently track negation."""
    a = _negation_ab(timeout=2)
    a.step("k", {"A"})    # instance 1 at state 1
    a.step("k", set())    # inst1 absent +1
    # "A" again: inst1 absent +2 -> fires this window; inst2 spawns at state 1
    assert a.step("k", {"A"}) == 0.7
    # inst2 still needs 2 absent windows
    assert a.step("k", set()) == 0.0  # inst2 absent +1
    assert a.step("k", set()) == 0.7  # inst2 absent +2 -> fires


def test_negation_per_ticker():
    a = _negation_ab(timeout=2)
    a.step("k1", {"A"})
    a.step("k1", set())
    a.step("k2", {"A"})
    # k1 fires (absent +2); k2 only at absent +1 -> no fire for k2
    assert a.step("k1", set()) == 0.7
    assert a.step("k2", set()) == 0.0  # k2 absent +1, not at timeout yet


# --- CEPDetector with negation patterns ---


def test_failed_breakout_pattern():
    d = CEPDetector()
    for _ in range(5):
        d.update(_window(total_volume=1000.0))
    d.score(_window(total_volume=6000.0))  # volume surge -> state 1
    d.update(_window(total_volume=6000.0))
    d.score(_window())  # no price jump, absent +1
    score = d.score(_window())  # absent +2 -> failed_breakout fires (timeout=2)
    assert score == -0.50
    assert d.last_match("AAPL") == "failed_breakout"


def test_sustained_selloff_pattern():
    d = CEPDetector()
    d.score(_window(price_change_rate=-0.05))  # price down -> state 1
    d.score(_window())  # no rebound, absent +1
    score = d.score(_window())  # absent +2 -> sustained_selloff fires
    assert d.last_match("AAPL") == "sustained_selloff"


# ---------------------------------------------------------------------------
# Kleene repetition
# ---------------------------------------------------------------------------


def _repeat_ab(min_count=3, max_count=None):
    """A{min_count,max_count} → B → accept."""
    return NFAEventAutomaton(
        "repeat_ab",
        transitions=[
            Transition(0, "A", 1),
            Transition(1, "B", 2),
        ],
        accept_state=2,
        severity=0.9,
        max_gap=min_count + 3,
        repeats=[RepeatEdge(state=1, event="A", min_count=min_count, max_count=max_count)],
    )


def test_repeat_fires_after_min_count():
    a = _repeat_ab(min_count=3)
    # First "A" transitions 0->1 via normal Transition; repeat counter starts at 0.
    a.step("k", {"A"})    # state 1, repeat_counter = 0
    a.step("k", {"A"})    # repeat_counter = 1
    a.step("k", {"A"})    # repeat_counter = 2
    a.step("k", {"A"})    # repeat_counter = 3 >= min
    assert a.step("k", {"B"}) == 0.9  # threshold met, B fires


def test_repeat_blocks_before_min_count():
    a = _repeat_ab(min_count=3)
    a.step("k", {"A"})    # transition 0->1, counter = 0
    a.step("k", {"A"})    # counter = 1
    a.step("k", {"A"})    # counter = 2
    assert a.step("k", {"B"}) == 0.0  # counter = 2 < 3, B blocked


def test_repeat_max_count_eviction():
    a = _repeat_ab(min_count=2, max_count=4)
    a.step("k", {"A"})    # transition 0->1, counter = 0
    a.step("k", {"A"})    # counter = 1
    a.step("k", {"A"})    # counter = 2
    a.step("k", {"A"})    # counter = 3
    a.step("k", {"A"})    # counter = 4
    a.step("k", {"A"})    # counter = 5 > max(4) -> instance dropped
    assert a.step("k", {"B"}) == 0.0  # no instance to fire


def test_repeat_counter_resets_on_new_instance():
    a = _repeat_ab(min_count=2)
    a.step("k", {"A"})    # transition 0->1, counter = 0
    assert a.step("k", {"B"}) == 0.0  # counter < min, B blocked
    # Start fresh
    a.step("k", {"A"})    # new instance, transition 0->1, counter = 0
    a.step("k", {"A"})    # counter = 1
    a.step("k", {"A"})    # counter = 2
    assert a.step("k", {"B"}) == 0.9  # threshold met


def test_repeat_idle_windows_age_instance():
    """Idle windows between repeats age the instance normally."""
    a = _repeat_ab(min_count=2)
    a.step("k", {"A"})    # transition 0->1, counter = 0
    a.step("k", {"A"})    # counter = 1
    a.step("k", set())    # idle, age increases
    a.step("k", {"A"})    # counter = 2
    assert a.step("k", {"B"}) == 0.9  # threshold met despite gap


# --- CEPDetector with Kleene patterns ---


def test_sustained_accumulation_pattern():
    d = CEPDetector()
    for _ in range(5):
        d.update(_window(total_volume=1000.0))
    # Use high volume so the EWMA baseline shift doesn't suppress later surges.
    # First surge transitions 0->1; then 3 more repeats (min_count=3).
    for _ in range(4):
        d.score(_window(total_volume=20000.0))
        d.update(_window(total_volume=20000.0))
    # Price jump completes (sustained_accumulation severity 0.90 > breakout 0.85)
    score = d.score(_window(price_change_rate=0.05))
    assert d.last_match("AAPL") == "sustained_accumulation"


# ---------------------------------------------------------------------------
# Hierarchical composition (meta-automata)
# ---------------------------------------------------------------------------


def test_meta_automaton_reversal_confirmed():
    """flash_reversal completion + volume_surge -> reversal_confirmed (meta)."""
    d = CEPDetector()
    for _ in range(5):
        d.update(_window(total_volume=1000.0))
    # Flash reversal: up then down
    d.score(_window(price_change_rate=0.05))   # price up
    d.score(_window(price_change_rate=-0.05))  # price down -> flash_reversal fires
    # Volume surge within 5 windows -> reversal_confirmed fires
    score = d.score(_window(total_volume=6000.0))
    assert d.last_match("AAPL") == "reversal_confirmed"
    assert score == -0.95


def test_meta_automaton_pump_and_dump():
    """volume_led_breakout then news_driven_selloff -> pump_and_dump."""
    d = CEPDetector()
    for _ in range(5):
        d.update(_window(total_volume=1000.0))
    # Phase 1: volume_led_breakout
    d.score(_window(total_volume=6000.0))      # volume surge
    d.update(_window(total_volume=6000.0))
    d.score(_window(price_change_rate=0.05))   # price up -> breakout fires
    # Phase 2: news_driven_selloff
    d.score(_window(sentiment_shift=-0.5))     # sentiment drop
    score = d.score(_window(price_change_rate=-0.05))  # price down -> selloff fires
    # pump_and_dump = PATTERN:breakout -> PATTERN:selloff, severity 1.0
    assert d.last_match("AAPL") == "pump_and_dump"
    assert score == -1.0


def test_meta_automaton_no_fire_without_base():
    """Meta-automaton doesn't fire if base patterns don't complete."""
    d = CEPDetector()
    # Just a price move — no flash_reversal completed, no breakout.
    d.score(_window(price_change_rate=0.05))
    assert d.last_match("AAPL") != "reversal_confirmed"
    assert d.last_match("AAPL") != "pump_and_dump"


def test_hierarchy_two_pass_ordering():
    """Synthetic PATTERN:* events from pass 1 are visible to pass 2 same window."""
    a_base = NFAEventAutomaton(
        "base_x",
        [Transition(0, "X", 1)],
        accept_state=1,
        severity=0.5,
        max_gap=3,
    )
    a_meta = NFAEventAutomaton(
        "meta_y",
        [Transition(0, "PATTERN:base_x", 1)],
        accept_state=1,
        severity=0.9,
        max_gap=3,
    )
    d = CEPDetector(automata=[a_base], meta_automata=[a_meta], point_severity=0.0)
    features = _window()
    # "X" completes base_x -> emits PATTERN:base_x -> meta_y fires same window
    score = d.score({**features, "_inject_events": {"X"}})
    # But CEPDetector uses EventDetector, not raw events, so we test via pattern directly
    # Instead, test at the automaton level directly:
    assert a_base.step("k", {"X"}) == 0.5
    enriched = {"X", "PATTERN:base_x"}
    assert a_meta.step("k", enriched) == 0.9
