"""Anomaly patterns expressed as finite-state automata.

Each automaton recognises an ordered sequence of primitive events. These are
the "complex events" of the CEP layer — multi-step market behaviours that a
point-wise detector cannot express. Severities are chosen so a confirmed
sequence outranks a lone primitive (see ``cep.cep_detector``).

The four patterns map onto the synthetic anomaly types used in the backtest
(``ml/backtest_anomalies.py``) and onto real market phenomena:

* ``volume_led_breakout`` — a volume surge immediately followed by a price jump
  (the classic breakout / pump leg). Catches ``volume_surge`` + ``multi_feature``.
* ``news_driven_selloff`` — a sentiment drop followed by a price fall
  (news leads price). Catches ``sentiment_crash`` that propagates into price.
* ``flash_reversal`` — a sharp move immediately retraced (up→down or down→up).
  A genuinely *temporal* pattern that point detectors miss.
* ``panic_compound`` — surge → sentiment drop → price fall, the canonical
  three-step A→B→C escalation. Highest severity.
"""

from cep.automaton import EventAutomaton, Transition
from cep.events import (
    PRICE_JUMP_DOWN,
    PRICE_JUMP_UP,
    SENTIMENT_DROP,
    VOLUME_SURGE,
)


def build_default_automata(max_gap: int = 3) -> list[EventAutomaton]:
    """Construct the default set of pattern automata.

    ``max_gap`` is the default temporal tolerance (in windows); patterns that
    should fire on tighter sequences override it with a smaller value.
    """
    return [
        EventAutomaton(
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
        EventAutomaton(
            name="news_driven_selloff",
            transitions=[
                Transition(0, SENTIMENT_DROP, 1),
                Transition(1, PRICE_JUMP_DOWN, 2),
            ],
            accept_state=2,
            severity=0.90,
            max_gap=max_gap,
        ),
        EventAutomaton(
            name="flash_reversal",
            transitions=[
                Transition(0, PRICE_JUMP_UP, 1),
                Transition(0, PRICE_JUMP_DOWN, 2),
                Transition(1, PRICE_JUMP_DOWN, 3),
                Transition(2, PRICE_JUMP_UP, 3),
            ],
            accept_state=3,
            severity=0.80,
            max_gap=2,
        ),
        EventAutomaton(
            name="panic_compound",
            transitions=[
                Transition(0, VOLUME_SURGE, 1),
                Transition(1, SENTIMENT_DROP, 2),
                Transition(2, PRICE_JUMP_DOWN, 3),
            ],
            accept_state=3,
            severity=1.0,
            max_gap=max_gap + 1,
        ),
    ]
