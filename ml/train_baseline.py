from config.logging_config import get_logger
from config.settings import settings
from ml.data_utils import download_historical
from ml.detector import AnomalyDetector, FEATURE_COLUMNS

log = get_logger("train_baseline")

MODEL_PATH = "data/models/isolation_forest.joblib"


def main():
    df = download_historical(settings.tickers)
    log.info("training_samples", count=len(df))

    if df.empty:
        log.error("no_training_data")
        return

    X = df[FEATURE_COLUMNS].values

    detector = AnomalyDetector()
    detector.fit(X)
    detector.save(MODEL_PATH)
    log.info("model_saved", path=MODEL_PATH)

    scores = detector.model.decision_function(X)
    predictions = detector.model.predict(X)
    n_anomalies = int((predictions == -1).sum())
    log.info(
        "training_summary",
        total=len(X),
        anomalies=n_anomalies,
        anomaly_rate=f"{n_anomalies / len(X):.2%}",
        score_mean=f"{scores.mean():.4f}",
        score_std=f"{scores.std():.4f}",
    )


if __name__ == "__main__":
    main()
