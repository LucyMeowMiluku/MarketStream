import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from shared import TICKERS, fetch_anomaly_data
from config.settings import settings

st.set_page_config(page_title="Anomaly Alerts — MarketStream", page_icon=":chart_with_upwards_trend:", layout="wide")

"""
# :material/warning: Anomaly Alerts
"""


cols = st.columns([1, 3])

with cols[0]:
    with st.container(border=True):
        ticker_filter = st.pills("Ticker", ["All"] + TICKERS, default="All")


@st.fragment(run_every=timedelta(seconds=5))
def alerts_panel():
    try:
        df = fetch_anomaly_data(ticker_filter)
    except Exception:
        st.error("Database connection lost. Retrying on next refresh...")
        return

    total = int(df.iloc[0]["total"]) if not df.empty else 0
    last_hour = int(df.iloc[0]["last_hour"]) if not df.empty else 0
    last_day = int(df.iloc[0]["last_day"]) if not df.empty else 0

    metric_cols = st.columns(3)
    with metric_cols[0]:
        with st.container(border=True):
            st.metric("Total Anomalies", total)
    with metric_cols[1]:
        with st.container(border=True):
            st.metric("Last Hour", last_hour)
    with metric_cols[2]:
        with st.container(border=True):
            st.metric("Last 24 Hours", last_day)

    if df.empty:
        st.info("No anomalies detected yet. The system is monitoring for unusual patterns.")
        return

    latest_time = df["detected_at"].max()
    if pd.notna(latest_time):
        ts = pd.Timestamp(latest_time)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        age = datetime.now(timezone.utc) - ts
        secs = int(age.total_seconds())
        age_str = f"{secs}s ago" if secs < 120 else f"{secs // 60}m ago"
        st.caption(f"Latest alert: {age_str}")

    with st.container(border=True):
        st.markdown("#### Recent Alerts")
        for _, row in df.iterrows():
            severity = "🔴" if row["anomaly_score"] < settings.anomaly_severity_threshold else "🟡"
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

                ds = row.get("detector_scores")
                if ds and isinstance(ds, dict):
                    st.markdown("**Per-Detector Scores**")
                    dcols = st.columns(len(ds))
                    for i, (name, val) in enumerate(ds.items()):
                        with dcols[i]:
                            st.metric(name, f"{val:.4f}")

    export_df = df[["detected_at", "ticker", "anomaly_score", "reason"]].copy()
    st.download_button("Download CSV", export_df.to_csv(index=False), "anomaly_alerts.csv", "text/csv")


alerts_panel()
