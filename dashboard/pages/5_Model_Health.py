import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import timedelta

import plotly.graph_objects as go
import streamlit as st

from shared import (
    PLOTLY_LAYOUT,
    TICKERS,
    fetch_anomaly_rate,
    fetch_detector_scores,
    fetch_drift_events,
    fetch_model_versions,
)

st.set_page_config(
    page_title="Model Health — MarketStream",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
)

"""
# :material/monitor_heart: Model Health
"""

cols = st.columns([1, 3])
with cols[0]:
    with st.container(border=True):
        ticker_filter = st.pills("Ticker", ["All"] + TICKERS, default="All")
        lookback = st.select_slider("Lookback (hours)", [6, 12, 24, 48], value=24)


@st.fragment(run_every=timedelta(seconds=10))
def health_panel():
    tab_registry, tab_drift, tab_rate, tab_detectors = st.tabs(
        ["Model Registry", "Drift Events", "Anomaly Rate", "Detector Scores"]
    )

    with tab_registry:
        versions = fetch_model_versions()
        if versions.empty:
            st.info("No model versions recorded yet. Run `uv run python -m ml.retrain` to create one.")
        else:
            for _, row in versions.iterrows():
                active = " :material/check_circle:" if row.get("is_active") else ""
                with st.expander(
                    f"v{row['version']} — {row['model_name']}{active}"
                ):
                    mcols = st.columns(4)
                    with mcols[0]:
                        st.metric("Samples", f"{row.get('sample_count', 0):,}")
                    with mcols[1]:
                        st.metric("Anomaly Rate", f"{row.get('anomaly_rate', 0):.2%}")
                    with mcols[2]:
                        st.metric("Score Mean", f"{row.get('score_mean', 0):.4f}")
                    with mcols[3]:
                        st.metric("Score Std", f"{row.get('score_std', 0):.4f}")
                    st.caption(f"Trained: {row['trained_at']} | Path: {row['model_path']}")

    with tab_drift:
        drift_df = fetch_drift_events(hours=lookback)
        if drift_df.empty:
            st.success("No drift events detected in the selected window.")
        else:
            st.metric("Drift Events", len(drift_df))
            layout = dict(**PLOTLY_LAYOUT)
            layout["yaxis"] = dict(gridcolor="#314158", zerolinecolor="#314158")
            fig = go.Figure(layout=layout)
            for ticker in drift_df["ticker"].unique():
                tdf = drift_df[drift_df["ticker"] == ticker]
                fig.add_trace(go.Scatter(
                    x=tdf["detected_at"],
                    y=tdf["feature_name"],
                    mode="markers",
                    marker=dict(size=10),
                    name=ticker,
                ))
            fig.update_layout(title="Drift Event Timeline", xaxis_title="Time", yaxis_title="Feature")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(drift_df, use_container_width=True)

    with tab_rate:
        rate_df = fetch_anomaly_rate(hours=lookback)
        if rate_df.empty:
            st.info("No feature data in the selected window.")
        else:
            rate_df["rate"] = rate_df["anomalies"] / rate_df["total"]
            layout = dict(**PLOTLY_LAYOUT)
            layout["yaxis"] = dict(gridcolor="#314158", zerolinecolor="#314158")
            fig = go.Figure(layout=layout)
            for ticker in rate_df["ticker"].unique():
                tdf = rate_df[rate_df["ticker"] == ticker]
                fig.add_trace(go.Scatter(
                    x=tdf["hour"], y=tdf["rate"], mode="lines+markers", name=ticker
                ))
            fig.update_layout(
                title="Rolling Anomaly Rate", xaxis_title="Time",
                yaxis_title="Anomaly Rate", yaxis_tickformat=".0%",
            )
            st.plotly_chart(fig, use_container_width=True)

    with tab_detectors:
        scores_df = fetch_detector_scores(ticker_filter, hours=lookback)
        if scores_df.empty:
            st.info("No ensemble scores recorded yet.")
        else:
            expanded = []
            for _, row in scores_df.iterrows():
                ds = row.get("detector_scores")
                if ds and isinstance(ds, dict):
                    expanded.append({
                        "time": row["window_end"],
                        "ticker": row["ticker"],
                        "ensemble": row["anomaly_score"],
                        **ds,
                    })
            if not expanded:
                st.info("No per-detector scores available.")
            else:
                import pandas as pd
                edf = pd.DataFrame(expanded)
                detector_cols = [c for c in edf.columns if c not in ("time", "ticker")]

                layout = dict(**PLOTLY_LAYOUT)
                layout["yaxis"] = dict(gridcolor="#314158", zerolinecolor="#314158")
                fig = go.Figure(layout=layout)
                for col in detector_cols:
                    fig.add_trace(go.Scatter(
                        x=edf["time"], y=edf[col], mode="lines", name=col
                    ))
                fig.update_layout(title="Detector Score Timelines", xaxis_title="Time", yaxis_title="Score")
                st.plotly_chart(fig, use_container_width=True)

                st.markdown("#### Detector Agreement")
                agree_cols = [c for c in detector_cols if c != "ensemble"]
                if len(agree_cols) >= 2:
                    threshold = -0.3
                    agreement = []
                    for _, row in edf.iterrows():
                        votes = [1 if row.get(c, 0) < threshold else 0 for c in agree_cols]
                        agreement.append(sum(votes) / len(votes))
                    edf["agreement"] = agreement
                    avg_agreement = sum(agreement) / len(agreement) if agreement else 0
                    st.metric("Avg Detector Agreement", f"{avg_agreement:.1%}")


health_panel()
