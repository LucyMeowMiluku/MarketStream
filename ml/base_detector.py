from abc import ABC, abstractmethod


class BaseDetector(ABC):
    @abstractmethod
    def score(self, features: dict) -> float:
        """Return anomaly score. Lower = more anomalous."""

    def update(self, features: dict) -> None:
        """Online learning update. No-op for batch detectors."""

    @property
    @abstractmethod
    def name(self) -> str: ...
