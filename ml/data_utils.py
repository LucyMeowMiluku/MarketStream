import numpy as np
import pandas as pd
import yfinance as yf

from config.logging_config import get_logger
from processing.feature_engine import price_change_rate

log = get_logger("data_utils")


def fetch_historical_sentiment(ticker: str, period: str = "30d") -> list[float]:
    """Fetch news headlines and generate synthetic sentiment distribution for training."""
    try:
        tk = yf.Ticker(ticker)
        news = tk.news or []
        if not news:
            return []
        scores = []
        for item in news:
            content = item.get("content", item)
            title = content.get("title", "")
            if title:
                scores.append(np.random.uniform(-0.3, 0.3))
        return scores
    except Exception as e:
        log.warning("sentiment_fetch_failed", ticker=ticker, error=str(e))
        return []


def download_historical(tickers: list[str], period: str = "30d") -> pd.DataFrame:
    """Download historical OHLCV data and compute training features."""
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

        sentiment_samples = fetch_historical_sentiment(ticker, period)
        rng = np.random.default_rng(42)

        window_size = 5
        for i in range(window_size, len(hist)):
            window = hist.iloc[i - window_size : i]
            first_close = float(window.iloc[0]["Close"])
            last_close = float(window.iloc[-1]["Close"])
            total_volume = int(window["Volume"].sum())

            if sentiment_samples:
                avg_sent = float(rng.choice(sentiment_samples))
                shift = float(rng.normal(0, 0.1))
            else:
                avg_sent = float(rng.normal(0, 0.15))
                shift = float(rng.normal(0, 0.08))

            all_features.append(
                {
                    "ticker": ticker,
                    "price_change_rate": price_change_rate(first_close, last_close),
                    "total_volume": total_volume,
                    "avg_sentiment": round(avg_sent, 4),
                    "sentiment_shift": round(shift, 4),
                }
            )

    return pd.DataFrame(all_features)
