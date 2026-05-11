from ml.base_detector import BaseDetector


class EnsembleDetector:
    """Weighted voting ensemble combining multiple anomaly detectors."""

    def __init__(
        self,
        detectors: list[BaseDetector],
        weights: list[float] | None = None,
        threshold: float = -0.3,
    ):
        self._detectors = detectors
        self._weights = weights or [1.0 / len(detectors)] * len(detectors)
        self._threshold = threshold

    def score(self, features: dict) -> tuple[float, dict[str, float]]:
        per_detector: dict[str, float] = {}
        weighted_sum = 0.0
        total_weight = 0.0

        for detector, weight in zip(self._detectors, self._weights):
            s = detector.score(features)
            per_detector[detector.name] = s
            if s != 0.0 or not _is_warmup_neutral(detector):
                weighted_sum += weight * s
                total_weight += weight

        avg = weighted_sum / total_weight if total_weight > 0 else 0.0
        return avg, per_detector

    def update(self, features: dict) -> None:
        for detector in self._detectors:
            detector.update(features)

    def is_anomaly(self, score: float) -> bool:
        return score < self._threshold

    @property
    def detector_names(self) -> list[str]:
        return [d.name for d in self._detectors]


def _is_warmup_neutral(detector: BaseDetector) -> bool:
    """Check if detector returned 0.0 because it's still warming up (LSTM)."""
    return detector.name == "lstm_ae"
