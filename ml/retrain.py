"""Scheduled retraining for IsolationForest with model versioning.

Usage:
    uv run python -m ml.retrain
"""

from datetime import datetime, timezone
from pathlib import Path

from config.logging_config import get_logger
from config.settings import settings
from ml.data_utils import download_historical
from ml.detector import AnomalyDetector, FEATURE_COLUMNS
from storage.db import get_session
from storage.models import ModelVersion

log = get_logger("retrain")

MODEL_DIR = Path("data/models")


def retrain(period: str = "30d") -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    df = download_historical(settings.tickers, period=period)
    log.info("training_samples", count=len(df))

    if df.empty:
        log.error("no_training_data")
        return

    X = df[FEATURE_COLUMNS].values

    detector = AnomalyDetector()
    detector.fit(X)

    X_scaled = detector._scaler.transform(X) if detector._scaler else X
    scores = detector.model.decision_function(X_scaled)
    predictions = detector.model.predict(X_scaled)
    n_anomalies = int((predictions == -1).sum())
    anomaly_rate = n_anomalies / len(X)

    session = get_session()
    try:
        latest = (
            session.query(ModelVersion)
            .filter(ModelVersion.model_name == "isolation_forest")
            .order_by(ModelVersion.version.desc())
            .first()
        )
        next_version = (latest.version + 1) if latest else 1

        model_path = str(MODEL_DIR / f"isolation_forest_v{next_version}.joblib")
        detector.save(model_path)

        if latest and latest.is_active:
            latest.is_active = False

        mv = ModelVersion(
            model_name="isolation_forest",
            version=next_version,
            trained_at=datetime.now(timezone.utc),
            sample_count=len(X),
            anomaly_rate=round(anomaly_rate, 4),
            score_mean=round(float(scores.mean()), 4),
            score_std=round(float(scores.std()), 4),
            model_path=model_path,
            is_active=True,
        )
        session.add(mv)
        session.commit()

        active_path = str(MODEL_DIR / "isolation_forest.joblib")
        detector.save(active_path)

        log.info(
            "retrain_complete",
            version=next_version,
            path=model_path,
            anomaly_rate=f"{anomaly_rate:.2%}",
            score_mean=f"{scores.mean():.4f}",
            score_std=f"{scores.std():.4f}",
        )
    finally:
        session.close()


if __name__ == "__main__":
    retrain()
