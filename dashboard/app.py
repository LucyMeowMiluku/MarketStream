import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from shared import TICKERS, engine

st.set_page_config(page_title="MarketStream", page_icon=":chart_with_upwards_trend:", layout="wide")

st.title("MarketStream")
st.caption("Explainable streaming anomaly detection: events → eight factors → six CEP state machines")

for column, title, caption in zip(
    st.columns(3),
    ("Price & Factors", "Sentiment Feed", "Anomaly Alerts"),
    ("Five-minute factor snapshots", "Timestamped market news", "Traceable CEP evidence"),
    strict=True,
):
    with column:
        with st.container(border=True):
            st.markdown(f"### {title}")
            st.caption(caption)

with st.container(border=True):
    st.markdown("#### Pipeline Health")
    try:
        snapshot_query = """
            SELECT ticker, MAX(event_time) AS last_snapshot,
                   COUNT(*) FILTER (WHERE event_time > NOW() - INTERVAL '1 hour') AS snapshots_last_hour
            FROM factor_snapshots GROUP BY ticker
        """
        snapshots = pd.read_sql(snapshot_query, engine())
        alerts = pd.read_sql(
            """SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE detected_at > NOW() - INTERVAL '1 hour') AS last_hour
               FROM anomaly_alerts""",
            engine(),
        )
        columns = st.columns(len(TICKERS))
        now = datetime.now(timezone.utc)
        for index, ticker in enumerate(TICKERS):
            row = snapshots[snapshots["ticker"] == ticker]
            with columns[index]:
                st.markdown(f"**{ticker}**")
                if row.empty or pd.isna(row.iloc[0]["last_snapshot"]):
                    st.caption("No snapshot")
                    continue
                timestamp = pd.Timestamp(row.iloc[0]["last_snapshot"])
                if timestamp.tzinfo is None:
                    timestamp = timestamp.tz_localize("UTC")
                age_minutes = (now - timestamp).total_seconds() / 60
                status = "LIVE" if age_minutes < 10 else "STALE" if age_minutes < 30 else "DOWN"
                st.metric(status, int(row.iloc[0]["snapshots_last_hour"]))
        st.caption(
            f"Stored alerts: {int(alerts.iloc[0]['total'])}; "
            f"last hour: {int(alerts.iloc[0]['last_hour'])}"
        )
    except Exception:
        st.info("Start TimescaleDB and the replay pipeline to populate this view.")

st.markdown("#### Core architecture")
st.code(
    "Alpaca / Replay → MarketEvent → Quality Gate → 8 Factors → 6 CEP State Machines → Alert",
    language=None,
)
