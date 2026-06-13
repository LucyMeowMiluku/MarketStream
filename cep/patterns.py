"""Anomaly patterns expressed as finite-state automata.

Each automaton recognises an ordered sequence of primitive events. These are
the "complex events" of the CEP layer — multi-step market behaviours that a
point-wise detector cannot express. Severities are chosen so a confirmed
sequence outranks a lone primitive (see ``cep.cep_detector``).

**Positive-sequence patterns** (fire when a sequence completes):

* ``volume_led_breakout`` — volume surge → price jump.
* ``news_driven_selloff`` — sentiment drop → price fall.
* ``flash_reversal`` — sharp move → immediate retrace.
* ``panic_compound`` — volume surge → sentiment drop → price fall.

**Negation patterns** (fire on event *absence*):

* ``failed_breakout`` — volume surge → NO price jump within 3 windows.
* ``sustained_selloff`` — price fall → NO rebound within 2 windows.

**Kleene patterns** (fire after repeated events):

* ``sustained_accumulation`` — volume surge ×3+ → price jump.
"""

from cep.automaton import (
    NegationEdge,
    NFAEventAutomaton,
    RepeatEdge,
    Transition,
)
from cep.events import (
    PRICE_JUMP_DOWN,
    PRICE_JUMP_UP,
    SENTIMENT_DROP,
    VOLUME_SURGE,
)
from cep.guards import feature_abs_gt, feature_gt


def build_default_automata(
    max_gap: int = 3,
) -> tuple[list[NFAEventAutomaton], list[NFAEventAutomaton]]:
    """Construct the default pattern automata.

    Returns ``(base_automata, meta_automata)``.  Base automata run first;
    when one reaches accept it emits a synthetic ``PATTERN:<name>`` event.
    Meta-automata run second on the enriched event set, enabling higher-order
    patterns that compose sub-pattern completions.
    """
    base = [
        # --- Positive-sequence patterns ---
        NFAEventAutomaton(
            name="volume_led_breakout",
            transitions=[
                Transition(0, VOLUME_SURGE, 1),
                Transition(1, PRICE_JUMP_UP, 2),
                Transition(1, PRICE_JUMP_DOWN, 2),
            ],
            accept_state=2,
            severity=0.85,
            max_gap=2,
        ),
        NFAEventAutomaton(
            name="news_driven_selloff",
            transitions=[
                Transition(0, SENTIMENT_DROP, 1),
                Transition(1, PRICE_JUMP_DOWN, 2),
            ],
            accept_state=2,
            severity=0.90,
            max_gap=max_gap,
        ),
        NFAEventAutomaton(
            name="flash_reversal",
            transitions=[
                Transition(0, PRICE_JUMP_UP, 1),
                Transition(0, PRICE_JUMP_DOWN, 2),
                Transition(1, PRICE_JUMP_DOWN, 3, max_gap=1),
                Transition(2, PRICE_JUMP_UP, 3, max_gap=1),
            ],
            accept_state=3,
            severity=0.80,
            max_gap=2,
        ),
        NFAEventAutomaton(
            name="panic_compound",
            transitions=[
                Transition(0, VOLUME_SURGE, 1),
                Transition(1, SENTIMENT_DROP, 2, max_gap=max_gap + 1),
                Transition(2, PRICE_JUMP_DOWN, 3, max_gap=2),
            ],
            accept_state=3,
            severity=1.0,
            max_gap=max_gap,
        ),
        # --- Negation patterns ---
        # Severity at 0.50: these advance meta-pattern state but do NOT
        # independently breach the anomaly threshold (score = -0.50 is NOT
        # < -0.50), avoiding the false-positive flood that "absence" patterns
        # cause on normal data.
        NFAEventAutomaton(
            name="failed_breakout",
            transitions=[
                Transition(0, VOLUME_SURGE, 1),
            ],
            accept_state=2,
            severity=0.50,
            max_gap=max_gap,
            negations=[
                NegationEdge(
                    from_state=1,
                    absent_event=PRICE_JUMP_UP,
                    to_state=2,
                    timeout=2,
                ),
            ],
        ),
        NFAEventAutomaton(
            name="sustained_selloff",
            transitions=[
                Transition(
                    0, PRICE_JUMP_DOWN, 1,
                    guard=feature_abs_gt("price_change_rate", 0.03),
                ),
            ],
            accept_state=2,
            severity=0.50,
            max_gap=max_gap,
            negations=[
                NegationEdge(
                    from_state=1,
                    absent_event=PRICE_JUMP_UP,
                    to_state=2,
                    timeout=2,
                ),
            ],
        ),
        # --- Kleene patterns ---
        NFAEventAutomaton(
            name="sustained_accumulation",
            transitions=[
                Transition(0, VOLUME_SURGE, 1),
                Transition(1, PRICE_JUMP_UP, 2),
                Transition(1, PRICE_JUMP_DOWN, 2),
            ],
            accept_state=2,
            severity=0.90,
            max_gap=2,
            repeats=[
                RepeatEdge(state=1, event=VOLUME_SURGE, min_count=3),
            ],
        ),
    ]

    PATTERN_FLASH = "PATTERN:flash_reversal"
    PATTERN_BREAKOUT = "PATTERN:volume_led_breakout"
    PATTERN_SELLOFF = "PATTERN:news_driven_selloff"

    meta = [
        # --- Hierarchical / compositional patterns ---
        NFAEventAutomaton(
            name="reversal_confirmed",
            transitions=[
                Transition(0, PATTERN_FLASH, 1),
                Transition(1, VOLUME_SURGE, 2),
            ],
            accept_state=2,
            severity=0.95,
            max_gap=5,
        ),
        NFAEventAutomaton(
            name="pump_and_dump",
            transitions=[
                Transition(0, PATTERN_BREAKOUT, 1),
                Transition(1, PATTERN_SELLOFF, 2),
            ],
            accept_state=2,
            severity=1.0,
            max_gap=10,
        ),
    ]

    return base, meta
