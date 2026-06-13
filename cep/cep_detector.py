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


class CEPDetector(BaseDetector):
    """Complex-event-processing anomaly detector (point rules + automata)."""

    def __init__(
        self,
        thresholds: EventThresholds | None = None,
        point_severity: float | None = None,
        max_gap: int | None = None,
        automata: list | None = None,
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
        self._automata = (
            automata
            if automata is not None
            else build_default_automata(
                max_gap=max_gap if max_gap is not None else settings.cep_max_gap
            )
        )
        self._point_severity = (
            point_severity
            if point_severity is not None
            else settings.cep_point_severity
        )
        # Most recent match per ticker — for the dashboard and the future
        # mixed-mode hook (CEP fires -> trigger heavier ML confirmation).
        self._last_match: dict[str, str] = {}

    @property
    def name(self) -> str:
        return "cep"

    def score(self, features: dict) -> float:
        ticker = features.get("ticker", "_default")
        events = self._events.detect(features)

        best_sev = 0.0
        best_name = ""
        for automaton in self._automata:
            sev = automaton.step(ticker, events)
            if sev > best_sev:
                best_sev = sev
                best_name = automaton.name

        # No full sequence completed, but a lone primitive is still a (weak)
        # anomaly under the simple-rule layer (disabled when point_severity == 0).
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
