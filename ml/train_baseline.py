import numpy as np
import pandas as pd
import yfinance as yf

from config.logging_config import get_logger
from config.settings import settings
from ml.detector import AnomalyDetector, FEATURE_COLUMNS
from processing.feature_engine import price_change_rate

log = get_logger("train_baseline")

MODEL_PATH = "data/models/isolation_forest.joblib"


def download_historical(tickers: list[str], period: str = "30d") -> pd.DataFrame:
    all_features = []

    for ticker in tickers:
        log.info("downloading", ticker=ticker, period=period)
        tk = yf.Ticker(ticker)
        hist = tk.history(period=period, interval="5m")
        if hist.empty:
            log.warning("no_data", ticker=ticker)
            continue

        hist = hist.reset_index()
        hist["ticker"] = ticker

        window_size = 5
        for i in range(window_size, len(hist)):
            window = hist.iloc[i - window_size : i]
            first_close = float(window.iloc[0]["Close"])
            last_close = float(window.iloc[-1]["Close"])
            total_volume = int(window["Volume"].sum())

            baseline_vol = float(hist.iloc[max(0, i - 20) : i]["Volume"].mean()) if i > 0 else 1.0

            all_features.append(
                {
                    "price_change_rate": price_change_rate(first_close, last_close),
                    "total_volume": total_volume,
                    "avg_sentiment": 0.0,
                    "sentiment_shift": 0.0,
                }
            )

    return pd.DataFrame(all_features)


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
