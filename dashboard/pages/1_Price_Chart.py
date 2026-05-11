import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from shared import PLOTLY_LAYOUT, TICKERS, fetch_price_data

st.set_page_config(page_title="Price Chart — MarketStream", page_icon=":chart_with_upwards_trend:", layout="wide")

"""
# :material/candlestick_chart: Price Chart
"""

cols = st.columns([1, 3])

with cols[0]:
    with st.container(border=True):
        ticker = st.pills("Ticker", TICKERS, default=TICKERS[0])
        lookback = st.select_slider(
            "Lookback",
            options=[1, 2, 4, 8, 12, 24],
            value=4,
            format_func=lambda x: f"{x}h",
        )


with cols[1]:

    @st.fragment(run_every=timedelta(seconds=5))
    def price_chart():
        try:
            df = fetch_price_data(ticker, lookback)
        except Exception:
            st.error("Database connection lost. Retrying on next refresh...")
            return

        if df.empty:
            st.info("No data yet. Start the pipeline and wait for the first window to close.")
            return

        latest_time = df["window_end"].max()
        if pd.notna(latest_time):
            ts = pd.Timestamp(latest_time)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            age = datetime.now(timezone.utc) - ts
            secs = int(age.total_seconds())
            age_str = f"{secs}s ago" if secs < 120 else f"{secs // 60}m ago"
            st.caption(f"Last update: {age_str}")

        with st.container(border=True):
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=df["window_end"],
                    y=df["avg_close"],
                    mode="lines+markers",
                    name="Avg Close",
                    line=dict(color="#615fff", width=2),
                    marker=dict(size=4),
                )
            )

            anomalies = df[df["is_anomaly"]]
            if not anomalies.empty:
                fig.add_trace(
                    go.Scatter(
                        x=anomalies["window_end"],
                        y=anomalies["avg_close"],
                        mode="markers",
                        name="Anomaly",
                        marker=dict(color="#ef4444", size=12, symbol="x"),
                    )
                )

            fig.update_layout(
                title=f"{ticker} — 5-Min Window Average Close",
                xaxis_title="Time",
                yaxis_title="Price ($)",
                height=420,
                **PLOTLY_LAYOUT,
            )
            st.plotly_chart(fig, use_container_width=True)

        metric_cols = st.columns(3)
        latest = df.iloc[-1]

        with metric_cols[0]:
            with st.container(border=True):
                price = f"${latest['avg_close']:.2f}" if pd.notna(latest["avg_close"]) else "N/A"
                st.metric("Current Price", price)
        with metric_cols[1]:
            with st.container(border=True):
                rate = latest["price_change_rate"]
                st.metric(
                    "Price Change Rate",
                    f"{rate:.2%}" if pd.notna(rate) else "N/A",
                    delta=f"{rate:.2%}" if pd.notna(rate) else None,
                )
        with metric_cols[2]:
            with st.container(border=True):
                score = latest["anomaly_score"]
                st.metric("Anomaly Score", f"{score:.4f}" if pd.notna(score) else "N/A")

        with st.container(border=True):
            st.markdown("#### Volume")
            vol_fig = go.Figure()
            colors = ["#ef4444" if a else "#615fff" for a in df["is_anomaly"]]
            vol_fig.add_trace(
                go.Bar(x=df["window_end"], y=df["total_volume"], marker_color=colors, name="Volume")
            )
            vol_fig.update_layout(
                xaxis_title="Time",
                yaxis_title="Volume",
                height=250,
                **PLOTLY_LAYOUT,
            )
            st.plotly_chart(vol_fig, use_container_width=True)

        st.download_button("Download CSV", df.to_csv(index=False), f"{ticker}_price_data.csv", "text/csv")

    price_chart()
