import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from datetime import timedelta

import pandas as pd
import streamlit as st

from storage.db import get_engine

st.set_page_config(page_title="Anomaly Alerts — MarketStream", page_icon=":chart_with_upwards_trend:", layout="wide")

"""
# :material/warning: Anomaly Alerts
"""


@st.cache_resource
def engine():
    return get_engine()


cols = st.columns([1, 3])

with cols[0]:
    with st.container(border=True):
        ticker_filter = st.pills("Ticker", ["All", "AAPL", "TSLA", "NVDA"], default="All")


@st.fragment(run_every=timedelta(seconds=5))
def alerts_panel():
    where = "WHERE ticker = %(ticker)s" if ticker_filter != "All" else ""
    params = {"ticker": ticker_filter} if ticker_filter != "All" else {}

    count_query = f"""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE detected_at > NOW() - INTERVAL '1 hour') as last_hour,
            COUNT(*) FILTER (WHERE detected_at > NOW() - INTERVAL '24 hours') as last_day
        FROM anomaly_alerts {where}
    """
    counts = pd.read_sql(count_query, engine(), params=params)

    metric_cols = st.columns(3)
    with metric_cols[0]:
        with st.container(border=True):
            st.metric("Total Anomalies", int(counts.iloc[0]["total"]))
    with metric_cols[1]:
        with st.container(border=True):
            st.metric("Last Hour", int(counts.iloc[0]["last_hour"]))
    with metric_cols[2]:
        with st.container(border=True):
            st.metric("Last 24 Hours", int(counts.iloc[0]["last_day"]))

    alerts_query = f"""
        SELECT detected_at, ticker, anomaly_score, reason, features
        FROM anomaly_alerts {where}
        ORDER BY detected_at DESC
        LIMIT 50
    """
    df = pd.read_sql(alerts_query, engine(), params=params)

    if df.empty:
        st.info("No anomalies detected yet. The system is monitoring for unusual patterns.")
        return

    with st.container(border=True):
        st.markdown("#### Recent Alerts")
        for _, row in df.iterrows():
            severity = "🔴" if row["anomaly_score"] < -0.3 else "🟡"
            with st.expander(
                f"{severity} {row['ticker']} — {row['detected_at'].strftime('%Y-%m-%d %H:%M:%S')} — Score: {row['anomaly_score']:.4f}"
            ):
                st.write(f"**Reason:** {row['reason']}")
                if row["features"]:
                    features = row["features"] if isinstance(row["features"], dict) else {}
                    fcols = st.columns(4)
                    with fcols[0]:
                        st.metric("Price Change", f"{features.get('price_change_rate', 0):.2%}")
                    with fcols[1]:
                        st.metric("Volume", f"{features.get('total_volume', 0):,}")
                    with fcols[2]:
                        st.metric("Avg Sentiment", f"{features.get('avg_sentiment', 0):.3f}")
                    with fcols[3]:
                        st.metric("Sentiment Shift", f"{features.get('sentiment_shift', 0):.3f}")


alerts_panel()
