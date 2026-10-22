"""The project's single offline machine-learning comparison baseline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from processing.event_models import FACTOR_GROUPS, FactorSnapshot

FACTOR_COLUMNS = tuple(FACTOR_GROUPS)


@dataclass(frozen=True, slots=True)
class BaselinePrediction:
    score: float
    is_anomaly: bool
    direction: str


class IsolationForestBaseline:
    """Fit once on train snapshots, then score without updating on test data."""

    def __init__(self, *, contamination: float = 0.05, random_state: int = 42):
        self.contamination = contamination
        self.random_state = random_state
        self._scaler = StandardScaler()
        self._model = IsolationForest(
            contamination=contamination,
            n_estimators=200,
            random_state=random_state,
        )
        self._fitted = False
        self.training_ended_at: datetime | None = None

    @staticmethod
    def _matrix(snapshots: list[FactorSnapshot]) -> np.ndarray:
        return np.asarray(
            [
                [float(snapshot.factor_values.get(name, 0.0)) for name in FACTOR_COLUMNS]
                for snapshot in snapshots
            ],
            dtype=float,
        )

    def fit(self, snapshots: list[FactorSnapshot]) -> None:
        if not snapshots:
            raise ValueError("Isolation Forest requires non-empty training snapshots")
        ordered = sorted(snapshots, key=lambda item: item.event_time)
        matrix = self._matrix(ordered)
        self._model.fit(self._scaler.fit_transform(matrix))
        self._fitted = True
        self.training_ended_at = ordered[-1].event_time

    def predict(self, snapshot: FactorSnapshot) -> BaselinePrediction:
        if not self._fitted:
            raise RuntimeError("Isolation Forest must be fitted before prediction")
        matrix = self._scaler.transform(self._matrix([snapshot]))
        raw_score = float(self._model.decision_function(matrix)[0])
        direction = "up" if snapshot.factor_values.get("return_surprise", 0.0) >= 0 else "down"
        return BaselinePrediction(
            score=raw_score,
            is_anomaly=bool(self._model.predict(matrix)[0] == -1),
            direction=direction,
        )
