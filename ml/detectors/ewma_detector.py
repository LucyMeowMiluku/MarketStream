import numpy as np

from ml.base_detector import BaseDetector

FEATURE_KEYS = ["price_change_rate", "total_volume", "avg_sentiment", "sentiment_shift"]


class EWMADetector(BaseDetector):
    """Exponentially Weighted Moving Average anomaly detector.

    Maintains running mean/variance per feature per ticker and scores
    new observations by their maximum z-score across features.
    """

    def __init__(self, span: int = 20):
        self._alpha = 2.0 / (span + 1)
        self._stats: dict[str, dict[str, tuple[float, float]]] = {}

    @property
    def name(self) -> str:
        return "ewma"

    def _get_key(self, features: dict) -> str:
        return features.get("ticker", "_default")

    def score(self, features: dict) -> float:
        key = self._get_key(features)
        if key not in self._stats:
            return 0.0

        stats = self._stats[key]
        z_scores = []
        for feat in FEATURE_KEYS:
            if feat not in stats:
                continue
            mean, var = stats[feat]
            std = np.sqrt(var) if var > 1e-10 else 1e-10
            val = float(features.get(feat, 0.0))
            z_scores.append(abs(val - mean) / std)

        if not z_scores:
            return 0.0

        return -max(z_scores)

    def update(self, features: dict) -> None:
        key = self._get_key(features)
        if key not in self._stats:
            self._stats[key] = {}

        stats = self._stats[key]
        alpha = self._alpha

        for feat in FEATURE_KEYS:
            val = float(features.get(feat, 0.0))
            if feat not in stats:
                stats[feat] = (val, 0.0)
            else:
                old_mean, old_var = stats[feat]
                new_mean = alpha * val + (1 - alpha) * old_mean
                new_var = (1 - alpha) * (old_var + alpha * (val - old_mean) ** 2)
                stats[feat] = (new_mean, new_var)
