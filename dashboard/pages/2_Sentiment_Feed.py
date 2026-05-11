import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from shared import PLOTLY_LAYOUT, TICKERS, fetch_sentiment_data

st.set_page_config(page_title="Sentiment Feed — MarketStream", page_icon=":chart_with_upwards_trend:", layout="wide")

"""
# :material/sentiment_satisfied: Sentiment Feed
"""

cols = st.columns([1, 3])

with cols[0]:
    with st.container(border=True):
        ticker = st.pills("Ticker", TICKERS, default=TICKERS[0])
        limit = st.select_slider(
            "Headlines",
            options=[10, 20, 30, 50, 100],
            value=30,
        )


with cols[1]:

    @st.fragment(run_every=timedelta(seconds=10))
    def sentiment_feed():
        try:
            df = fetch_sentiment_data(ticker, limit)
        except Exception:
            st.error("Database connection lost. Retrying on next refresh...")
            return

        if df.empty:
            st.info("No sentiment data yet. Start the news producer and wait for headlines.")
            return

        latest_time = df["time"].max()
        if pd.notna(latest_time):
            ts = pd.Timestamp(latest_time)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            age = datetime.now(timezone.utc) - ts
            secs = int(age.total_seconds())
            age_str = f"{secs}s ago" if secs < 120 else f"{secs // 60}m ago"
            st.caption(f"Last update: {age_str}")

        with st.container(border=True):
            df_sorted = df.iloc[::-1]
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=df_sorted["time"],
                    y=df_sorted["sentiment_score"],
                    mode="lines+markers",
                    name="Sentiment",
                    line=dict(width=2, color="#615fff"),
                    marker=dict(
                        size=8,
                        color=df_sorted["sentiment_score"],
                        colorscale=[[0, "#ef4444"], [0.5, "#64748b"], [1, "#22c55e"]],
                        cmin=-1,
                        cmax=1,
                    ),
                )
            )
            fig.add_hline(y=0, line_dash="dash", line_color="#64748b", opacity=0.5)
            layout = {**PLOTLY_LAYOUT}
            layout["yaxis"] = dict(range=[-1.1, 1.1], gridcolor="#314158", zerolinecolor="#314158")
            fig.update_layout(
                title=f"{ticker} — Sentiment Over Time",
                xaxis_title="Time",
                yaxis_title="Sentiment Score",
                height=380,
                **layout,
            )
            st.plotly_chart(fig, use_container_width=True)

        pos = len(df[df["sentiment_label"] == "positive"])
        neg = len(df[df["sentiment_label"] == "negative"])
        neu = len(df[df["sentiment_label"] == "neutral"])
        avg = df["sentiment_score"].mean()

        metric_cols = st.columns(4)
        with metric_cols[0]:
            with st.container(border=True):
                st.metric("Avg Score", f"{avg:.3f}" if pd.notna(avg) else "N/A")
        with metric_cols[1]:
            with st.container(border=True):
                st.metric("Positive", pos)
        with metric_cols[2]:
            with st.container(border=True):
                st.metric("Negative", neg)
        with metric_cols[3]:
            with st.container(border=True):
                st.metric("Neutral", neu)

        with st.container(border=True):
            st.markdown("#### Latest Headlines")
            display_df = df[["time", "headline", "source", "sentiment_score", "sentiment_label"]].copy()
            display_df.columns = ["Time", "Headline", "Source", "Score", "Label"]
            st.dataframe(display_df, use_container_width=True, height=400)

        st.download_button("Download CSV", df.to_csv(index=False), f"{ticker}_sentiment.csv", "text/csv")

    sentiment_feed()
