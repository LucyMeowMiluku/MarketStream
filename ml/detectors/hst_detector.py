from river.anomaly import HalfSpaceTrees

from ml.base_detector import BaseDetector

FEATURE_KEYS = ["price_change_rate", "total_volume", "avg_sentiment", "sentiment_shift"]


class HSTDetector(BaseDetector):
    """Streaming Half-Space Trees anomaly detector (via river).

    A true streaming variant of Isolation Forest that updates
    incrementally with each data point—no batch retraining needed.
    """

    def __init__(self, n_trees: int = 25, height: int = 6, window_size: int = 50):
        self._model = HalfSpaceTrees(
            n_trees=n_trees,
            height=height,
            window_size=window_size,
            seed=42,
        )
        self._n_seen = 0

    @property
    def name(self) -> str:
        return "hst"

    def _extract(self, features: dict) -> dict:
        return {k: float(features.get(k, 0.0)) for k in FEATURE_KEYS}

    def score(self, features: dict) -> float:
        x = self._extract(features)
        raw = self._model.score_one(x)
        return -min(raw * 3.0, 1.0)

    def update(self, features: dict) -> None:
        x = self._extract(features)
        self._model.learn_one(x)
        self._n_seen += 1
