import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from shared import TICKERS, engine

st.set_page_config(
    page_title="MarketStream",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
)

"""
# :material/query_stats: MarketStream

Multi-source streaming analytics for financial trends & anomaly detection.
"""

""

cols = st.columns(3)

with cols[0]:
    with st.container(border=True):
        st.markdown("### :material/candlestick_chart: Price Chart")
        st.caption("Real-time price trends with anomaly markers")

with cols[1]:
    with st.container(border=True):
        st.markdown("### :material/sentiment_satisfied: Sentiment Feed")
        st.caption("Rolling news headlines with FinBERT sentiment scores")

with cols[2]:
    with st.container(border=True):
        st.markdown("### :material/warning: Anomaly Alerts")
        st.caption("Detected anomalies with feature details")

""

with st.container(border=True):
    st.markdown("#### System Health")
    try:
        health_query = """
            SELECT
                ticker,
                MAX(window_end) as last_feature,
                COUNT(*) FILTER (WHERE window_end > NOW() - INTERVAL '1 hour') as features_last_hour
            FROM feature_vectors
            GROUP BY ticker
        """
        fv_health = pd.read_sql(health_query, engine())

        sentiment_query = """
            SELECT
                ticker,
                MAX(time) as last_sentiment,
                COUNT(*) FILTER (WHERE time > NOW() - INTERVAL '1 hour') as sentiments_last_hour
            FROM sentiment_scores
            GROUP BY ticker
        """
        sent_health = pd.read_sql(sentiment_query, engine())

        anomaly_query = """
            SELECT COUNT(*) as total,
                   COUNT(*) FILTER (WHERE detected_at > NOW() - INTERVAL '1 hour') as last_hour
            FROM anomaly_alerts
        """
        anom_health = pd.read_sql(anomaly_query, engine())

        health_cols = st.columns(len(TICKERS))
        now = datetime.now(timezone.utc)
        for i, ticker in enumerate(TICKERS):
            with health_cols[i]:
                fv_row = fv_health[fv_health["ticker"] == ticker]
                sent_row = sent_health[sent_health["ticker"] == ticker]

                if not fv_row.empty and pd.notna(fv_row.iloc[0]["last_feature"]):
                    last_ts = pd.Timestamp(fv_row.iloc[0]["last_feature"])
                    if last_ts.tzinfo is None:
                        last_ts = last_ts.tz_localize("UTC")
                    age_mins = (now - last_ts).total_seconds() / 60
                    if age_mins < 10:
                        status = ":green-background[LIVE]"
                    elif age_mins < 30:
                        status = ":orange-background[STALE]"
                    else:
                        status = ":red-background[DOWN]"
                    features_count = int(fv_row.iloc[0]["features_last_hour"])
                else:
                    status = ":red-background[NO DATA]"
                    features_count = 0

                sent_count = int(sent_row.iloc[0]["sentiments_last_hour"]) if not sent_row.empty else 0

                st.markdown(f"**{ticker}** {status}")
                st.caption(f"Features/hr: {features_count} | Headlines/hr: {sent_count}")

        anom_total = int(anom_health.iloc[0]["last_hour"]) if not anom_health.empty else 0
        st.caption(f"Anomalies detected in last hour: {anom_total}")

    except Exception:
        st.info("Database not available. Start the pipeline to see system health.")

""

with st.container(border=True):
    st.markdown("#### Architecture")
    st.code(
        "yfinance → Kafka → Quix Streams (5-min windows) → IsolationForest → TimescaleDB → Streamlit",
        language=None,
    )
    tech = st.columns(4)
    tech[0].markdown("**Ingestion**\n\nyfinance + FinBERT")
    tech[1].markdown("**Streaming**\n\nKafka + Quix Streams")
    tech[2].markdown("**ML**\n\nIsolation Forest")
    tech[3].markdown("**Storage**\n\nTimescaleDB")
