"""CEP anomaly detector — a low-latency alternative to the ML ensemble.

Combines two layers:

1. **Point rules (simple indicators).** A lone primitive event (a 2% price
   jump, a 3x volume surge, a sentiment drop) raises a weak anomaly. This is the
   interpretable "simple threshold" baseline and gives the detector recall on
   isolated point anomalies.
2. **State automata (complex events).** Ordered sequences of primitives —
   recognised by the automata in :mod:`cep.patterns` — raise a strong anomaly.
   This is the novel CEP contribution: it expresses temporal/compound patterns a
   point detector cannot, with higher precision.

The detector implements :class:`ml.base_detector.BaseDetector`, so it drops into
the existing :class:`ml.ensemble.EnsembleDetector` and the ``ml/backtest.py``
evaluation harness unchanged — enabling an apples-to-apples comparison with the
ML baseline on the same data and metrics.

Per-window call contract (matches the ensemble / replay loop): ``score()`` is
called exactly once, then ``update()`` once. ``score()`` advances the automata
(emitting a detection on the window that completes a pattern) using the *current*
volume baseline; ``update()`` then folds this window into that baseline. So every
event is judged against history, never against itself.
"""

from cep.events import EventDetector, EventThresholds
from cep.patterns import build_default_automata
from config.settings import settings
from ml.base_detector import BaseDetector

PATTERN_PREFIX = "PATTERN:"


class CEPDetector(BaseDetector):
    """Complex-event-processing anomaly detector (point rules + automata).

    Supports **hierarchical composition**: base automata run first, and any
    that reach their accept state emit a synthetic ``PATTERN:<name>`` event.
    Meta-automata then run on the enriched event set, enabling higher-order
    patterns that consume sub-pattern completions as inputs.
    """

    def __init__(
        self,
        thresholds: EventThresholds | None = None,
        point_severity: float | None = None,
        max_gap: int | None = None,
        automata: list | None = None,
        meta_automata: list | None = None,
    ):
        self._events = EventDetector(
            thresholds
            or EventThresholds(
                price_jump=settings.cep_price_jump,
                volume_surge_ratio=settings.cep_volume_surge_ratio,
                sentiment_shift=settings.cep_sentiment_shift,
                sentiment_floor=settings.cep_sentiment_floor,
                volume_ewma_span=settings.cep_volume_ewma_span,
                min_volume_obs=settings.cep_min_volume_obs,
            )
        )
        gap = max_gap if max_gap is not None else settings.cep_max_gap
        if automata is not None:
            self._automata = automata
            self._meta_automata: list = meta_automata or []
        else:
            base, meta = build_default_automata(max_gap=gap)
            self._automata = base
            self._meta_automata = meta
        self._point_severity = (
            point_severity
            if point_severity is not None
            else settings.cep_point_severity
        )
        self._last_match: dict[str, str] = {}

    @property
    def name(self) -> str:
        return "cep"

    def score(self, features: dict) -> float:
        ticker = features.get("ticker", "_default")
        events = self._events.detect(features)

        best_sev = 0.0
        best_name = ""

        # Pass 1: base automata
        fired: set[str] = set()
        for automaton in self._automata:
            sev = automaton.step(ticker, events, features=features)
            if sev > 0:
                fired.add(f"{PATTERN_PREFIX}{automaton.name}")
            if sev > best_sev:
                best_sev = sev
                best_name = automaton.name

        # Pass 2: meta-automata consume synthetic PATTERN:* events.
        # Use >= so meta-patterns win ties (they are more specific).
        if self._meta_automata:
            enriched = events | fired
            for meta in self._meta_automata:
                sev = meta.step(ticker, enriched, features=features)
                if sev > 0 and sev >= best_sev:
                    best_sev = sev
                    best_name = meta.name

        if best_sev == 0.0 and events and self._point_severity > 0.0:
            best_sev = self._point_severity
            best_name = "point:" + "+".join(sorted(events))

        if best_sev > 0.0:
            self._last_match[ticker] = best_name
        else:
            self._last_match.pop(ticker, None)

        return -best_sev

    def update(self, features: dict) -> None:
        self._events.update(features)

    def last_match(self, ticker: str = "_default") -> str | None:
        """The pattern (or ``point:...``) that fired on this ticker's last window."""
        return self._last_match.get(ticker)
