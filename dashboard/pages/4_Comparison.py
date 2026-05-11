import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from shared import PLOTLY_LAYOUT, TICKERS, engine

st.set_page_config(page_title="Comparison — MarketStream", page_icon=":chart_with_upwards_trend:", layout="wide")

"""
# :material/compare_arrows: Ticker Comparison
"""

cols = st.columns([1, 3])

with cols[0]:
    with st.container(border=True):
        selected = st.multiselect("Compare Tickers", TICKERS, default=TICKERS[:2])
        lookback = st.select_slider(
            "Lookback",
            options=[1, 2, 4, 8, 12, 24],
            value=4,
            format_func=lambda x: f"{x}h",
        )

COLORS = ["#615fff", "#22c55e", "#ef4444", "#f59e0b", "#06b6d4"]


@st.fragment(run_every=timedelta(seconds=10))
def comparison_view():
    if len(selected) < 2:
        st.info("Select at least 2 tickers to compare.")
        return

    try:
        price_query = """
            SELECT window_end, ticker, avg_close, price_change_rate, total_volume,
                   anomaly_score, is_anomaly
            FROM feature_vectors
            WHERE ticker = ANY(%(tickers)s)
              AND window_end > NOW() - %(lookback)s * INTERVAL '1 hour'
            ORDER BY window_end
        """
        df = pd.read_sql(price_query, engine(), params={"tickers": selected, "lookback": lookback})

        sent_query = """
            SELECT time, ticker, sentiment_score
            FROM sentiment_scores
            WHERE ticker = ANY(%(tickers)s)
              AND time > NOW() - %(lookback)s * INTERVAL '1 hour'
            ORDER BY time
        """
        sent_df = pd.read_sql(sent_query, engine(), params={"tickers": selected, "lookback": lookback})
    except Exception:
        st.error("Database connection lost. Retrying on next refresh...")
        return

    if df.empty:
        st.info("No data yet. Start the pipeline and wait for the first window to close.")
        return

    with cols[1]:
        with st.container(border=True):
            fig = make_subplots(
                rows=3,
                cols=1,
                shared_xaxes=True,
                vertical_spacing=0.06,
                subplot_titles=("Price (Avg Close)", "Volume", "Sentiment"),
                row_heights=[0.45, 0.25, 0.30],
            )

            for i, ticker in enumerate(selected):
                color = COLORS[i % len(COLORS)]
                tdf = df[df["ticker"] == ticker]
                if tdf.empty:
                    continue

                fig.add_trace(
                    go.Scatter(
                        x=tdf["window_end"],
                        y=tdf["avg_close"],
                        mode="lines+markers",
                        name=f"{ticker} Price",
                        line=dict(color=color, width=2),
                        marker=dict(size=3),
                    ),
                    row=1,
                    col=1,
                )

                fig.add_trace(
                    go.Bar(
                        x=tdf["window_end"],
                        y=tdf["total_volume"],
                        name=f"{ticker} Vol",
                        marker_color=color,
                        opacity=0.7,
                    ),
                    row=2,
                    col=1,
                )

                sdf = sent_df[sent_df["ticker"] == ticker]
                if not sdf.empty:
                    fig.add_trace(
                        go.Scatter(
                            x=sdf["time"],
                            y=sdf["sentiment_score"],
                            mode="lines+markers",
                            name=f"{ticker} Sent",
                            line=dict(color=color, width=1.5),
                            marker=dict(size=4),
                        ),
                        row=3,
                        col=1,
                    )

            layout = {**PLOTLY_LAYOUT}
            fig.update_layout(
                height=700,
                template=layout["template"],
                paper_bgcolor=layout["paper_bgcolor"],
                plot_bgcolor=layout["plot_bgcolor"],
                font=layout["font"],
            )
            for ax in ["xaxis", "xaxis2", "xaxis3", "yaxis", "yaxis2", "yaxis3"]:
                fig.update_layout(
                    **{ax: dict(gridcolor="#314158", zerolinecolor="#314158")}
                )

            st.plotly_chart(fig, use_container_width=True)

    summary_cols = st.columns(len(selected))
    for i, ticker in enumerate(selected):
        tdf = df[df["ticker"] == ticker]
        if tdf.empty:
            continue
        latest = tdf.iloc[-1]
        with summary_cols[i]:
            with st.container(border=True):
                st.markdown(f"**{ticker}**")
                price = f"${latest['avg_close']:.2f}" if pd.notna(latest["avg_close"]) else "N/A"
                st.metric("Price", price)
                rate = latest["price_change_rate"]
                st.metric(
                    "Change",
                    f"{rate:.2%}" if pd.notna(rate) else "N/A",
                    delta=f"{rate:.2%}" if pd.notna(rate) else None,
                )
                anomalies = len(tdf[tdf["is_anomaly"]])
                st.metric("Anomalies", anomalies)


comparison_view()
