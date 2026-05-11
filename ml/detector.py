import numpy as np
import joblib
from pathlib import Path
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from ml.base_detector import BaseDetector


FEATURE_COLUMNS = ["price_change_rate", "total_volume", "avg_sentiment", "sentiment_shift"]


class AnomalyDetector(BaseDetector):
    def __init__(self, model_path: str | None = None):
        if model_path:
            self.model = joblib.load(model_path)
            scaler_path = model_path.replace('.joblib', '_scaler.joblib')
            self._scaler = joblib.load(scaler_path) if Path(scaler_path).exists() else None
        else:
            self.model = IsolationForest(
                contamination=0.05,
                n_estimators=200,
                random_state=42,
            )
            self._scaler = None
        self._is_fitted = model_path is not None

    @property
    def name(self) -> str:
        return "isolation_forest"

    def fit(self, X: np.ndarray):
        self._scaler = StandardScaler()
        X_scaled = self._scaler.fit_transform(X)
        self.model.fit(X_scaled)
        self._is_fitted = True

    def score(self, features: dict) -> float:
        X = np.array([[features.get(col, 0.0) for col in FEATURE_COLUMNS]])
        if self._scaler is not None:
            X = self._scaler.transform(X)
        raw = float(self.model.decision_function(X)[0])
        if raw >= 0:
            return 0.0
        return max(-1.0, raw / 0.15)

    def predict(self, features: dict) -> tuple[float, bool]:
        X = np.array([[features.get(col, 0.0) for col in FEATURE_COLUMNS]])
        if self._scaler is not None:
            X = self._scaler.transform(X)
        raw = float(self.model.decision_function(X)[0])
        is_anomaly = self.model.predict(X)[0] == -1
        normalized = 0.0 if raw >= 0 else max(-1.0, raw / 0.15)
        return normalized, bool(is_anomaly)

    def save(self, path: str):
        joblib.dump(self.model, path)
        if self._scaler is not None:
            joblib.dump(self._scaler, path.replace('.joblib', '_scaler.joblib'))
