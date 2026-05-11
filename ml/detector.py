import numpy as np
import joblib
from sklearn.ensemble import IsolationForest

from ml.base_detector import BaseDetector


FEATURE_COLUMNS = ["price_change_rate", "total_volume", "avg_sentiment", "sentiment_shift"]


class AnomalyDetector(BaseDetector):
    def __init__(self, model_path: str | None = None):
        if model_path:
            self.model = joblib.load(model_path)
        else:
            self.model = IsolationForest(
                contamination=0.05,
                n_estimators=200,
                random_state=42,
            )
        self._is_fitted = model_path is not None

    @property
    def name(self) -> str:
        return "isolation_forest"

    def fit(self, X: np.ndarray):
        self.model.fit(X)
        self._is_fitted = True

    def score(self, features: dict) -> float:
        X = np.array([[features.get(col, 0.0) for col in FEATURE_COLUMNS]])
        return float(self.model.decision_function(X)[0])

    def predict(self, features: dict) -> tuple[float, bool]:
        X = np.array([[features.get(col, 0.0) for col in FEATURE_COLUMNS]])
        score = float(self.model.decision_function(X)[0])
        is_anomaly = self.model.predict(X)[0] == -1
        return score, bool(is_anomaly)

    def save(self, path: str):
        joblib.dump(self.model, path)
