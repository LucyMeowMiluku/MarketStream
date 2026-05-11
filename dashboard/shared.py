import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st

from config.settings import settings
from storage.db import get_engine

TICKERS = settings.tickers

PLOTLY_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Space Grotesk, sans-serif", color="#e2e8f0"),
    xaxis=dict(gridcolor="#314158", zerolinecolor="#314158"),
    yaxis=dict(gridcolor="#314158", zerolinecolor="#314158"),
    margin=dict(l=0, r=0, t=40, b=0),
)


@st.cache_resource
def engine():
    return get_engine()


@st.cache_data(ttl=30)
def fetch_price_data(ticker: str, lookback: int) -> pd.DataFrame:
    query = """
        SELECT window_end, avg_close, price_change_rate, total_volume,
               anomaly_score, is_anomaly
        FROM feature_vectors
        WHERE ticker = %(ticker)s
          AND window_end > NOW() - %(lookback)s * INTERVAL '1 hour'
        ORDER BY window_end
    """
    return pd.read_sql(query, engine(), params={"ticker": ticker, "lookback": lookback})


@st.cache_data(ttl=30)
def fetch_sentiment_data(ticker: str, limit: int) -> pd.DataFrame:
    query = """
        SELECT time, ticker, headline, source, sentiment_score, sentiment_label
        FROM sentiment_scores
        WHERE ticker = %(ticker)s
        ORDER BY time DESC
        LIMIT %(limit)s
    """
    return pd.read_sql(query, engine(), params={"ticker": ticker, "limit": limit})


@st.cache_data(ttl=30)
def fetch_anomaly_data(ticker_filter: str) -> pd.DataFrame:
    where = "WHERE ticker = %(ticker)s" if ticker_filter != "All" else ""
    params = {"ticker": ticker_filter} if ticker_filter != "All" else {}
    query = f"""
        WITH recent_alerts AS (
            SELECT detected_at, ticker, anomaly_score, reason, features, detector_scores
            FROM anomaly_alerts {where}
            ORDER BY detected_at DESC
            LIMIT 50
        )
        SELECT *,
            (SELECT COUNT(*) FROM anomaly_alerts {where}) as total,
            (SELECT COUNT(*) FROM anomaly_alerts {where + (" AND" if where else "WHERE")} detected_at > NOW() - INTERVAL '1 hour') as last_hour,
            (SELECT COUNT(*) FROM anomaly_alerts {where + (" AND" if where else "WHERE")} detected_at > NOW() - INTERVAL '24 hours') as last_day
        FROM recent_alerts
    """
    return pd.read_sql(query, engine(), params=params)


@st.cache_data(ttl=30)
def fetch_model_versions() -> pd.DataFrame:
    query = """
        SELECT id, model_name, version, trained_at, sample_count,
               anomaly_rate, score_mean, score_std, model_path, is_active
        FROM model_versions
        ORDER BY trained_at DESC
        LIMIT 20
    """
    return pd.read_sql(query, engine())


@st.cache_data(ttl=30)
def fetch_drift_events(hours: int = 24) -> pd.DataFrame:
    query = """
        SELECT detected_at, ticker, feature_name, drift_type, details
        FROM drift_events
        WHERE detected_at > NOW() - %(hours)s * INTERVAL '1 hour'
        ORDER BY detected_at DESC
    """
    return pd.read_sql(query, engine(), params={"hours": hours})


@st.cache_data(ttl=30)
def fetch_detector_scores(ticker_filter: str, hours: int = 6) -> pd.DataFrame:
    where = "AND ticker = %(ticker)s" if ticker_filter != "All" else ""
    params = {"hours": hours}
    if ticker_filter != "All":
        params["ticker"] = ticker_filter
    query = f"""
        SELECT window_end, ticker, anomaly_score, is_anomaly, detector_scores
        FROM feature_vectors
        WHERE window_end > NOW() - %(hours)s * INTERVAL '1 hour'
          {where}
          AND detector_scores IS NOT NULL
        ORDER BY window_end
    """
    return pd.read_sql(query, engine(), params=params)


@st.cache_data(ttl=30)
def fetch_anomaly_rate(hours: int = 24) -> pd.DataFrame:
    query = """
        SELECT
            date_trunc('hour', window_end) as hour,
            ticker,
            COUNT(*) as total,
            SUM(CASE WHEN is_anomaly THEN 1 ELSE 0 END) as anomalies
        FROM feature_vectors
        WHERE window_end > NOW() - %(hours)s * INTERVAL '1 hour'
        GROUP BY hour, ticker
        ORDER BY hour
    """
    return pd.read_sql(query, engine(), params={"hours": hours})
