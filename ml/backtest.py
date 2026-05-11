"""Offline backtest for MarketStream anomaly detection pipeline.

Downloads historical data, trains models, injects synthetic anomalies,
replays through the full ensemble, and evaluates detection performance.

Usage:
    uv run python -m ml.backtest
    uv run python -m ml.backtest --period 60d --injection-rate 0.1
"""

import argparse
import json
import time
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from statistics import mean, median

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
import yfinance as yf

from config.logging_config import get_logger
from config.settings import settings
from ml.backtest_anomalies import AnomalyInjector, InjectedAnomaly
from ml.detector import AnomalyDetector, FEATURE_COLUMNS
from ml.detectors.ewma_detector import EWMADetector
from ml.detectors.hst_detector import HSTDetector
from ml.detectors.lstm_detector import LSTMDetector, LSTMAutoencoder
from ml.drift_monitor import DriftMonitor
from ml.ensemble import EnsembleDetector
from processing.feature_engine import price_change_rate

log = get_logger("backtest")

FEATURE_KEYS = ["price_change_rate", "total_volume", "avg_sentiment", "sentiment_shift"]

PLOTLY_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Space Grotesk, sans-serif", color="#e2e8f0"),
    xaxis=dict(gridcolor="#314158", zerolinecolor="#314158"),
    yaxis=dict(gridcolor="#314158", zerolinecolor="#314158"),
    margin=dict(l=60, r=20, t=50, b=40),
)


# ---------------------------------------------------------------------------
# Data Preparation
# ---------------------------------------------------------------------------


def download_raw_ohlcv(tickers: list[str], period: str = "60d") -> pd.DataFrame:
    frames = []
    for ticker in tickers:
        log.info("downloading", ticker=ticker, period=period)
        tk = yf.Ticker(ticker)
        hist = tk.history(period=period, interval="5m")
        if hist.empty:
            log.warning("no_data", ticker=ticker)
            continue
        hist = hist.reset_index()
        hist["ticker"] = ticker
        for col in ("Datetime", "Date"):
            if col in hist.columns:
                hist = hist.rename(columns={col: "timestamp"})
                break
        frames.append(hist)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def compute_features_from_ohlcv(
    ohlcv_df: pd.DataFrame,
    ticker: str,
    window_size: int = 5,
    rng_seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(rng_seed)
    ticker_df = ohlcv_df[ohlcv_df["ticker"] == ticker].reset_index(drop=True)
    rows: list[dict] = []

    for i in range(window_size, len(ticker_df)):
        window = ticker_df.iloc[i - window_size : i]
        first_close = float(window.iloc[0]["Close"])
        last_close = float(window.iloc[-1]["Close"])
        total_volume = float(window["Volume"].sum())
        avg_close = float(window["Close"].mean())

        avg_sent = float(rng.normal(0, 0.15))
        shift = float(rng.normal(0, 0.08))

        rows.append(
            {
                "ticker": ticker,
                "timestamp": window.iloc[-1]["timestamp"],
                "avg_close": round(avg_close, 4),
                "price_change_rate": price_change_rate(first_close, last_close),
                "total_volume": total_volume,
                "avg_sentiment": round(avg_sent, 4),
                "sentiment_shift": round(shift, 4),
            }
        )
    return pd.DataFrame(rows)


def train_test_split_temporal(
    df: pd.DataFrame, train_ratio: float = 0.7
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_parts, test_parts = [], []
    for ticker in df["ticker"].unique():
        tdf = df[df["ticker"] == ticker].sort_values("timestamp").reset_index(drop=True)
        split_idx = int(len(tdf) * train_ratio)
        train_parts.append(tdf.iloc[:split_idx])
        test_parts.append(tdf.iloc[split_idx:])
    return (
        pd.concat(train_parts, ignore_index=True),
        pd.concat(test_parts, ignore_index=True),
    )


# ---------------------------------------------------------------------------
# Model Training
# ---------------------------------------------------------------------------


def _create_sequences(data: np.ndarray, seq_len: int) -> np.ndarray:
    return np.array([data[i : i + seq_len] for i in range(len(data) - seq_len + 1)])


def train_models(train_df: pd.DataFrame, model_dir: Path) -> dict:
    model_dir.mkdir(parents=True, exist_ok=True)
    summary: dict = {}

    X = train_df[FEATURE_COLUMNS].values

    # --- Isolation Forest ---
    detector = AnomalyDetector()
    detector.fit(X)
    detector.save(str(model_dir / "isolation_forest.joblib"))
    scores = detector.model.decision_function(X)
    preds = detector.model.predict(X)
    n_anom = int((preds == -1).sum())
    summary["isolation_forest"] = {
        "samples": len(X),
        "anomalies": n_anom,
        "anomaly_rate": round(n_anom / len(X), 4),
        "score_mean": round(float(scores.mean()), 4),
        "score_std": round(float(scores.std()), 4),
    }
    log.info("if_trained", **summary["isolation_forest"])

    # --- LSTM Autoencoder ---
    all_seqs: list[np.ndarray] = []
    for ticker in train_df["ticker"].unique():
        vals = (
            train_df[train_df["ticker"] == ticker][FEATURE_KEYS]
            .values.astype(np.float32)
        )
        if len(vals) >= settings.lstm_sequence_length:
            all_seqs.append(_create_sequences(vals, settings.lstm_sequence_length))

    if all_seqs:
        sequences = np.concatenate(all_seqs, axis=0)
        seq_mean = sequences.reshape(-1, len(FEATURE_KEYS)).mean(axis=0)
        seq_std = sequences.reshape(-1, len(FEATURE_KEYS)).std(axis=0) + 1e-8
        sequences_norm = (sequences - seq_mean) / seq_std

        loader = DataLoader(
            TensorDataset(torch.tensor(sequences_norm)), batch_size=32, shuffle=True
        )
        model = LSTMAutoencoder(
            input_dim=len(FEATURE_KEYS), hidden_dim=settings.lstm_hidden_dim
        )
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        criterion = nn.MSELoss()

        model.train()
        final_loss = 0.0
        for epoch in range(30):
            total_loss = 0.0
            for (batch,) in loader:
                optimizer.zero_grad()
                loss = criterion(model(batch), batch)
                loss.backward()
                optimizer.step()
                total_loss += loss.item() * batch.size(0)
            final_loss = total_loss / len(sequences_norm)
            if (epoch + 1) % 10 == 0:
                log.info("lstm_epoch", epoch=epoch + 1, loss=f"{final_loss:.6f}")

        torch.save(model.state_dict(), str(model_dir / "lstm_autoencoder.pt"))
        np.savez(str(model_dir / "lstm_norm.npz"), mean=seq_mean, std=seq_std)
        summary["lstm"] = {"sequences": len(sequences_norm), "final_loss": round(final_loss, 6)}
        log.info("lstm_trained", **summary["lstm"])

    return summary


# ---------------------------------------------------------------------------
# Ensemble Construction
# ---------------------------------------------------------------------------


class OfflineDriftMonitor(DriftMonitor):
    """DriftMonitor that logs drift events locally instead of writing to DB."""

    def __init__(self, delta: float = 0.002):
        super().__init__(delta=delta)
        self.drift_log: list[dict] = []

    def _record_drift(self, ticker: str, feature_name: str) -> None:
        self.drift_log.append({"ticker": ticker, "feature_name": feature_name})


def build_backtest_ensemble(model_dir: Path) -> EnsembleDetector:
    detectors = []
    weights = list(settings.ensemble_weights)

    detectors.append(EWMADetector(span=settings.ewma_span))
    detectors.append(
        HSTDetector(
            n_trees=settings.hst_n_trees,
            height=settings.hst_height,
            window_size=settings.hst_window_size,
        )
    )
    detectors.append(AnomalyDetector(model_path=str(model_dir / "isolation_forest.joblib")))

    lstm_path = model_dir / "lstm_autoencoder.pt"
    lstm = LSTMDetector(
        model_path=str(lstm_path) if lstm_path.exists() else None,
        sequence_length=settings.lstm_sequence_length,
        hidden_dim=settings.lstm_hidden_dim,
    )
    norm_path = model_dir / "lstm_norm.npz"
    if norm_path.exists():
        norms = np.load(str(norm_path))
        lstm._mean = norms["mean"]
        lstm._std = norms["std"]
    detectors.append(lstm)

    return EnsembleDetector(
        detectors, weights=weights, threshold=settings.ensemble_threshold
    )


def _build_anomaly_reason(features: dict, score: float) -> str:
    reasons: list[str] = []
    if abs(features.get("price_change_rate", 0)) > settings.anomaly_price_threshold:
        reasons.append(f"large price move ({features['price_change_rate']:.2%})")
    if features.get("total_volume", 0) > settings.anomaly_volume_threshold:
        reasons.append(f"high volume ({features['total_volume']:,.0f})")
    if abs(features.get("sentiment_shift", 0)) > settings.anomaly_sentiment_threshold:
        reasons.append(f"sentiment shift ({features['sentiment_shift']:.2f})")
    if not reasons:
        reasons.append(f"anomaly score={score:.4f}")
    return "; ".join(reasons)


# ---------------------------------------------------------------------------
# Scoring Replay
# ---------------------------------------------------------------------------


@dataclass
class ScoringResult:
    index: int
    ticker: str
    timestamp: str
    ensemble_score: float
    detector_scores: dict
    is_anomaly: bool
    reason: str


def replay_scoring(
    test_df: pd.DataFrame,
    ensemble: EnsembleDetector,
    drift_monitor: OfflineDriftMonitor,
    train_df: pd.DataFrame,
) -> list[ScoringResult]:
    # Warm up per-ticker streaming state from training data
    for ticker in train_df["ticker"].unique():
        tail = train_df[train_df["ticker"] == ticker].tail(50)
        for _, row in tail.iterrows():
            feat = row.to_dict()
            ensemble.update(feat)
            drift_monitor.update(feat)

    results: list[ScoringResult] = []
    n = len(test_df)
    for count, (idx, row) in enumerate(test_df.iterrows()):
        feat = row.to_dict()
        score, det_scores = ensemble.score(feat)
        is_anom = ensemble.is_anomaly(score)
        ensemble.update(feat)
        drift_monitor.update(feat)

        results.append(
            ScoringResult(
                index=int(idx),
                ticker=str(feat["ticker"]),
                timestamp=str(feat.get("timestamp", "")),
                ensemble_score=float(score),
                detector_scores={k: float(v) for k, v in det_scores.items()},
                is_anomaly=is_anom,
                reason=_build_anomaly_reason(feat, score),
            )
        )
        if (count + 1) % 500 == 0:
            log.info("replay_progress", done=count + 1, total=n)

    return results


# ---------------------------------------------------------------------------
# Evaluation Metrics
# ---------------------------------------------------------------------------


@dataclass
class BacktestMetrics:
    precision: float
    recall: float
    f1: float
    false_positive_rate: float
    detection_latency_mean: float
    detection_latency_median: float
    total_detections: int
    total_ground_truth: int
    true_positives: int
    false_positives: int
    false_negatives: int
    per_type_recall: dict
    per_detector_metrics: dict


def compute_metrics(
    results: list[ScoringResult],
    ground_truth: list[InjectedAnomaly],
    threshold: float = -0.3,
    tolerance: int = 2,
) -> BacktestMetrics:
    gt_indices = {a.index for a in ground_truth}
    det_indices = {r.index for r in results if r.is_anomaly}

    matched_gt: set[int] = set()
    matched_det: set[int] = set()
    latencies: list[int] = []

    for d in sorted(det_indices):
        for offset in range(tolerance + 1):
            matched = False
            for g in (d - offset, d + offset):
                if g in gt_indices and g not in matched_gt:
                    matched_gt.add(g)
                    matched_det.add(d)
                    latencies.append(abs(d - g))
                    matched = True
                    break
            if matched:
                break

    tp = len(matched_gt)
    fp = len(det_indices - matched_det)
    fn = len(gt_indices - matched_gt)
    total_normal = len(results) - len(gt_indices)

    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    fpr = fp / total_normal if total_normal > 0 else 0.0

    type_groups: dict[str, list[int]] = defaultdict(list)
    for a in ground_truth:
        type_groups[a.anomaly_type].append(a.index)
    per_type = {
        t: round(sum(1 for i in idxs if i in matched_gt) / len(idxs), 4)
        for t, idxs in type_groups.items()
    }

    per_det: dict[str, dict] = {}
    if results:
        for name in results[0].detector_scores:
            dd = {r.index for r in results if r.detector_scores.get(name, 0) < threshold}
            dtp = len(dd & gt_indices)
            dfp = len(dd - gt_indices)
            dfn = len(gt_indices - dd)
            dp = dtp / (dtp + dfp) if (dtp + dfp) > 0 else 0.0
            dr = dtp / (dtp + dfn) if (dtp + dfn) > 0 else 0.0
            df1 = 2 * dp * dr / (dp + dr) if (dp + dr) > 0 else 0.0
            per_det[name] = {
                "precision": round(dp, 4),
                "recall": round(dr, 4),
                "f1": round(df1, 4),
                "detections": len(dd),
            }

    return BacktestMetrics(
        precision=round(prec, 4),
        recall=round(rec, 4),
        f1=round(f1, 4),
        false_positive_rate=round(fpr, 6),
        detection_latency_mean=round(mean(latencies), 2) if latencies else 0.0,
        detection_latency_median=round(median(latencies), 2) if latencies else 0.0,
        total_detections=len(det_indices),
        total_ground_truth=len(ground_truth),
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        per_type_recall=per_type,
        per_detector_metrics=per_det,
    )


def compute_score_statistics(
    results: list[ScoringResult], ground_truth: list[InjectedAnomaly]
) -> dict:
    gt_idx = {a.index for a in ground_truth}
    all_s = [r.ensemble_score for r in results]
    anom_s = [r.ensemble_score for r in results if r.index in gt_idx]
    norm_s = [r.ensemble_score for r in results if r.index not in gt_idx]

    stats: dict = {
        "ensemble_mean": round(float(np.mean(all_s)), 4),
        "ensemble_std": round(float(np.std(all_s)), 4),
    }
    if anom_s and norm_s:
        pooled = float(np.sqrt((np.var(anom_s) + np.var(norm_s)) / 2))
        stats["cohens_d"] = (
            round(abs(float(np.mean(norm_s)) - float(np.mean(anom_s))) / pooled, 4)
            if pooled > 0
            else 0.0
        )
        stats["anomaly_score_mean"] = round(float(np.mean(anom_s)), 4)
        stats["normal_score_mean"] = round(float(np.mean(norm_s)), 4)

    if results:
        for name in results[0].detector_scores:
            vals = [r.detector_scores[name] for r in results]
            stats[f"{name}_mean"] = round(float(np.mean(vals)), 4)
            stats[f"{name}_std"] = round(float(np.std(vals)), 4)
    return stats


# ---------------------------------------------------------------------------
# Drift Detection Test
# ---------------------------------------------------------------------------


def test_drift_detection(test_df: pd.DataFrame) -> dict:
    df = test_df.sort_values("timestamp").reset_index(drop=True)
    n = len(df)
    shift_start = int(n * 0.8)

    for i in range(shift_start, n):
        df.at[i, "price_change_rate"] = float(df.at[i, "price_change_rate"]) * 3.0
        df.at[i, "total_volume"] = float(df.at[i, "total_volume"]) * 2.0
        df.at[i, "avg_sentiment"] = float(df.at[i, "avg_sentiment"]) - 0.3

    monitor = OfflineDriftMonitor(delta=settings.drift_sensitivity)
    first_drift: dict[str, int] = {}

    for idx, row in df.iterrows():
        drifted = monitor.update(row.to_dict())
        if drifted and int(idx) >= shift_start:
            for feat in drifted:
                if feat not in first_drift:
                    first_drift[feat] = int(idx) - shift_start

    return {
        "shift_start_index": shift_start,
        "total_rows": n,
        "detection_latency": first_drift,
        "total_drift_events": len(monitor.drift_log),
    }


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------


def generate_plots(
    output_dir: Path,
    results: list[ScoringResult],
    ground_truth: list[InjectedAnomaly],
    metrics: BacktestMetrics,
    drift_monitor: OfflineDriftMonitor,
) -> None:
    _plot_score_timeline(output_dir, results, ground_truth)
    _plot_score_distributions(output_dir, results, ground_truth)
    _plot_detection_summary(output_dir, metrics)
    _plot_detector_agreement(output_dir, results, ground_truth)
    _plot_drift_timeline(output_dir, results, drift_monitor)
    log.info("plots_saved", dir=str(output_dir))


def _layout(**overrides) -> dict:
    base = dict(PLOTLY_LAYOUT)
    base.update(overrides)
    return base


def _plot_score_timeline(
    output_dir: Path,
    results: list[ScoringResult],
    ground_truth: list[InjectedAnomaly],
) -> None:
    tickers = sorted({r.ticker for r in results})
    fig = make_subplots(rows=len(tickers), cols=1, subplot_titles=tickers, shared_xaxes=True)
    colors = {"ewma": "#60a5fa", "hst": "#34d399", "isolation_forest": "#fbbf24", "lstm_ae": "#f472b6"}

    for row_i, ticker in enumerate(tickers, 1):
        tr = [r for r in results if r.ticker == ticker]
        g2l = {r.index: j for j, r in enumerate(tr)}
        x = list(range(len(tr)))

        fig.add_trace(
            go.Scatter(x=x, y=[r.ensemble_score for r in tr], name="Ensemble",
                       line=dict(width=1.5, color="#e2e8f0"), showlegend=(row_i == 1)),
            row=row_i, col=1,
        )
        for name in (tr[0].detector_scores if tr else {}):
            fig.add_trace(
                go.Scatter(x=x, y=[r.detector_scores[name] for r in tr], name=name,
                           line=dict(width=0.7, dash="dot", color=colors.get(name, "#94a3b8")),
                           opacity=0.5, showlegend=(row_i == 1)),
                row=row_i, col=1,
            )

        fig.add_hline(y=settings.ensemble_threshold, line_dash="dash",
                      line_color="red", row=row_i, col=1)

        gt_local = [g2l[a.index] for a in ground_truth if a.ticker == ticker and a.index in g2l]
        if gt_local:
            fig.add_trace(
                go.Scatter(x=gt_local, y=[tr[j].ensemble_score for j in gt_local],
                           mode="markers", marker=dict(color="red", size=7, symbol="x"),
                           name="Injected", showlegend=(row_i == 1)),
                row=row_i, col=1,
            )

    fig.update_layout(**_layout(title="Anomaly Score Timeline", height=300 * len(tickers)))
    fig.write_html(str(output_dir / "score_timeline.html"))


def _plot_score_distributions(
    output_dir: Path,
    results: list[ScoringResult],
    ground_truth: list[InjectedAnomaly],
) -> None:
    gt_idx = {a.index for a in ground_truth}
    normal = [r.ensemble_score for r in results if r.index not in gt_idx]
    anomaly = [r.ensemble_score for r in results if r.index in gt_idx]

    fig = go.Figure()
    fig.add_trace(go.Histogram(x=normal, name="Normal", opacity=0.7, marker_color="#60a5fa", nbinsx=50))
    fig.add_trace(go.Histogram(x=anomaly, name="Injected", opacity=0.7, marker_color="#ef4444", nbinsx=30))
    fig.add_vline(x=settings.ensemble_threshold, line_dash="dash", line_color="yellow",
                  annotation_text="threshold")

    fig.update_layout(**_layout(title="Score Distributions", barmode="overlay",
                                xaxis=dict(title="Anomaly Score", gridcolor="#314158"),
                                yaxis=dict(title="Count", gridcolor="#314158")))
    fig.write_html(str(output_dir / "score_distributions.html"))


def _plot_detection_summary(output_dir: Path, metrics: BacktestMetrics) -> None:
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=[
            f"Detection Counts (P={metrics.precision:.2f} R={metrics.recall:.2f} F1={metrics.f1:.2f})",
            "Per-Type Recall",
        ],
    )
    fig.add_trace(
        go.Bar(x=["TP", "FP", "FN"], y=[metrics.true_positives, metrics.false_positives, metrics.false_negatives],
               marker_color=["#34d399", "#ef4444", "#fbbf24"]),
        row=1, col=1,
    )
    types = list(metrics.per_type_recall.keys())
    fig.add_trace(
        go.Bar(x=types, y=[metrics.per_type_recall[t] for t in types], marker_color="#60a5fa"),
        row=1, col=2,
    )
    fig.update_layout(**_layout(title="Detection Performance", showlegend=False))
    fig.write_html(str(output_dir / "detection_matrix.html"))


def _plot_detector_agreement(
    output_dir: Path,
    results: list[ScoringResult],
    ground_truth: list[InjectedAnomaly],
) -> None:
    gt_idx = {a.index for a in ground_truth}
    key_points = [r for r in results if r.is_anomaly or r.index in gt_idx]
    if not key_points:
        return

    det_names = list(key_points[0].detector_scores.keys())
    x_labels = [f"{r.ticker}:{r.index}" for r in key_points]
    z = [[r.detector_scores.get(d, 0.0) for r in key_points] for d in det_names]

    fig = go.Figure(
        go.Heatmap(z=z, x=x_labels, y=det_names, colorscale="RdBu", zmid=0,
                    colorbar=dict(title="Score"))
    )
    fig.update_layout(**_layout(title="Detector Scores at Key Points", height=350,
                                xaxis=dict(title="Point", gridcolor="#314158")))
    fig.write_html(str(output_dir / "detector_agreement.html"))


def _plot_drift_timeline(
    output_dir: Path,
    results: list[ScoringResult],
    drift_monitor: OfflineDriftMonitor,
) -> None:
    if not drift_monitor.drift_log:
        return

    feat_colors = {
        "price_change_rate": "#ef4444",
        "total_volume": "#fbbf24",
        "avg_sentiment": "#60a5fa",
        "sentiment_shift": "#34d399",
    }
    fig = go.Figure()
    for entry in drift_monitor.drift_log:
        feat = entry["feature_name"]
        fig.add_trace(
            go.Scatter(
                x=[entry.get("index", 0)], y=[feat],
                mode="markers", marker=dict(size=10, color=feat_colors.get(feat, "#94a3b8")),
                name=feat, showlegend=False,
            )
        )

    for i, entry in enumerate(drift_monitor.drift_log):
        entry["index"] = i

    tickers_feats = defaultdict(list)
    for e in drift_monitor.drift_log:
        tickers_feats[e["feature_name"]].append(e["index"])

    fig = go.Figure()
    for feat, idxs in tickers_feats.items():
        fig.add_trace(
            go.Scatter(
                x=idxs, y=[feat] * len(idxs), mode="markers",
                marker=dict(size=10, color=feat_colors.get(feat, "#94a3b8")),
                name=feat,
            )
        )

    fig.update_layout(**_layout(title="Drift Events During Replay", height=300,
                                xaxis=dict(title="Event Index", gridcolor="#314158")))
    fig.write_html(str(output_dir / "drift_timeline.html"))


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


class _Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def save_summary(
    output_dir: Path,
    args: argparse.Namespace,
    metrics: BacktestMetrics,
    score_stats: dict,
    training_summary: dict,
    drift_result: dict,
    drift_monitor: OfflineDriftMonitor,
) -> None:
    summary = {
        "config": {
            "period": args.period,
            "train_ratio": args.train_ratio,
            "injection_rate": args.injection_rate,
            "seed": args.seed,
            "tickers": args.tickers or settings.tickers,
            "threshold": settings.ensemble_threshold,
        },
        "training": training_summary,
        "metrics": asdict(metrics),
        "score_statistics": score_stats,
        "drift_test": drift_result,
        "drift_events_during_replay": len(drift_monitor.drift_log),
    }
    path = output_dir / "summary.json"
    path.write_text(json.dumps(summary, indent=2, cls=_Encoder))
    log.info("summary_saved", path=str(path))


def print_summary(metrics: BacktestMetrics, score_stats: dict) -> None:
    sep = "=" * 50
    print(f"\n{sep}")
    print("  BACKTEST RESULTS")
    print(sep)
    print(f"  Precision:  {metrics.precision:.4f}")
    print(f"  Recall:     {metrics.recall:.4f}")
    print(f"  F1 Score:   {metrics.f1:.4f}")
    print(f"  FP Rate:    {metrics.false_positive_rate:.6f}")
    print(f"  Cohen's d:  {score_stats.get('cohens_d', 'N/A')}")
    print(f"  Detections: {metrics.total_detections}  Ground Truth: {metrics.total_ground_truth}")
    print(f"  TP={metrics.true_positives}  FP={metrics.false_positives}  FN={metrics.false_negatives}")
    print()
    print("  Per-Type Recall:")
    for t, r in metrics.per_type_recall.items():
        print(f"    {t:20s} {r:.4f}")
    print()
    print("  Per-Detector Standalone:")
    for name, m in metrics.per_detector_metrics.items():
        print(f"    {name:20s} P={m['precision']:.2f}  R={m['recall']:.2f}  F1={m['f1']:.2f}")
    print(sep + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MarketStream Backtest")
    p.add_argument("--period", default="60d")
    p.add_argument("--train-ratio", type=float, default=0.7)
    p.add_argument("--injection-rate", type=float, default=0.05)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--output-dir", default="data/backtest_results")
    p.add_argument("--tickers", nargs="+", default=None)
    p.add_argument("--skip-plots", action="store_true")
    p.add_argument("--threshold", type=float, default=None)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    tickers = args.tickers or settings.tickers
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.threshold is not None:
        settings.ensemble_threshold = args.threshold

    t0 = time.time()

    # 1. Download raw OHLCV
    log.info("downloading", tickers=tickers, period=args.period)
    raw_df = download_raw_ohlcv(tickers, period=args.period)
    if raw_df.empty:
        log.error("no_data_downloaded")
        return
    log.info("downloaded", rows=len(raw_df))

    # 2. Compute features per ticker
    features_df = pd.concat(
        [compute_features_from_ohlcv(raw_df, t, rng_seed=args.seed) for t in tickers],
        ignore_index=True,
    )
    log.info("features_computed", rows=len(features_df))

    # 3. Train/test split
    train_df, test_df = train_test_split_temporal(features_df, train_ratio=args.train_ratio)
    log.info("split", train=len(train_df), test=len(test_df))

    # 4. Train models
    model_dir = output_dir / "models"
    training_summary = train_models(train_df, model_dir)

    # 5. Inject synthetic anomalies
    injector = AnomalyInjector(seed=args.seed, injection_rate=args.injection_rate)
    test_injected, ground_truth = injector.inject(test_df)
    type_counts = defaultdict(int)
    for a in ground_truth:
        type_counts[a.anomaly_type] += 1
    log.info("injected", total=len(ground_truth), types=dict(type_counts))

    # 6. Build ensemble from backtest-trained models
    ensemble = build_backtest_ensemble(model_dir)
    log.info("ensemble_built", detectors=ensemble.detector_names)

    # 7. Replay scoring
    drift_monitor = OfflineDriftMonitor(delta=settings.drift_sensitivity)
    results = replay_scoring(test_injected, ensemble, drift_monitor, train_df)
    log.info("replay_done", scored=len(results), drift_events=len(drift_monitor.drift_log))

    # 8. Evaluate
    metrics = compute_metrics(results, ground_truth, threshold=settings.ensemble_threshold)
    score_stats = compute_score_statistics(results, ground_truth)

    # 9. Drift detection test
    drift_result = test_drift_detection(test_df)
    log.info("drift_test_done", **drift_result)

    # 10. Save outputs
    save_summary(output_dir, args, metrics, score_stats, training_summary, drift_result, drift_monitor)
    if not args.skip_plots:
        generate_plots(output_dir, results, ground_truth, metrics, drift_monitor)

    # 11. Console summary
    elapsed = time.time() - t0
    log.info("backtest_complete", elapsed=f"{elapsed:.1f}s")
    print_summary(metrics, score_stats)


if __name__ == "__main__":
    main()
