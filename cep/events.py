"""Primitive event detection — the "simple indicators" of the CEP layer.

Maps each window's feature vector to a set of primitive market events that the
state automata consume to recognise complex, multi-step anomaly patterns.

Design notes
------------
* **Price and sentiment** use absolute, interpretable thresholds (a 2% move is a
  2% move regardless of ticker), so they need no warm-up.
* **Volume** scale spans orders of magnitude across tickers, so it uses an
  adaptive per-ticker EWMA baseline and fires on a surge *ratio*. The baseline
  is updated in :meth:`EventDetector.update`, called *after* scoring, so an
  event is always judged against history — never against itself.
"""

from dataclasses import dataclass

# Primitive event types (string constants — JSON-friendly, match codebase style).
PRICE_JUMP_UP = "price_jump_up"
PRICE_JUMP_DOWN = "price_jump_down"
VOLUME_SURGE = "volume_surge"
SENTIMENT_DROP = "sentiment_drop"
SENTIMENT_SPIKE = "sentiment_spike"

ALL_EVENTS = (
    PRICE_JUMP_UP,
    PRICE_JUMP_DOWN,
    VOLUME_SURGE,
    SENTIMENT_DROP,
    SENTIMENT_SPIKE,
)


@dataclass
class EventThresholds:
    price_jump: float = 0.02
    volume_surge_ratio: float = 3.0
    sentiment_shift: float = 0.3
    sentiment_floor: float = -0.5
    volume_ewma_span: int = 20
    min_volume_obs: int = 3


class EventDetector:
    """Turns a window's features into a set of primitive events.

    Stateless w.r.t. price/sentiment; keeps a per-ticker EWMA volume baseline.
    """

    def __init__(self, thresholds: EventThresholds | None = None):
        self._t = thresholds or EventThresholds()
        self._alpha = 2.0 / (self._t.volume_ewma_span + 1)
        self._vol_mean: dict[str, float] = {}
        self._vol_obs: dict[str, int] = {}

    def detect(self, features: dict) -> set[str]:
        events: set[str] = set()
        t = self._t

        pcr = float(features.get("price_change_rate", 0.0))
        if pcr >= t.price_jump:
            events.add(PRICE_JUMP_UP)
        elif pcr <= -t.price_jump:
            events.add(PRICE_JUMP_DOWN)

        ticker = features.get("ticker", "_default")
        vol = float(features.get("total_volume", 0.0))
        mean = self._vol_mean.get(ticker)
        obs = self._vol_obs.get(ticker, 0)
        if mean is not None and obs >= t.min_volume_obs and mean > 0:
            if vol / mean >= t.volume_surge_ratio:
                events.add(VOLUME_SURGE)

        shift = float(features.get("sentiment_shift", 0.0))
        avg_sent = float(features.get("avg_sentiment", 0.0))
        if shift <= -t.sentiment_shift or avg_sent <= t.sentiment_floor:
            events.add(SENTIMENT_DROP)
        elif shift >= t.sentiment_shift:
            events.add(SENTIMENT_SPIKE)

        return events

    def update(self, features: dict) -> None:
        ticker = features.get("ticker", "_default")
        vol = float(features.get("total_volume", 0.0))
        mean = self._vol_mean.get(ticker)
        if mean is None:
            self._vol_mean[ticker] = vol
        else:
            self._vol_mean[ticker] = self._alpha * vol + (1 - self._alpha) * mean
        self._vol_obs[ticker] = self._vol_obs.get(ticker, 0) + 1
