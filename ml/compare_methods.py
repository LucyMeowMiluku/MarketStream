"""Head-to-head comparison: CEP (complex event processing) vs the ML ensemble.

Runs both detection methods through the *same* injected-anomaly backtest and
reports detection quality (precision / recall / F1 / FP-rate / per-type recall)
AND per-window latency. The latency numbers quantify the "real-time" claim that
the project has so far only asserted, and are where the lightweight CEP approach
is expected to decisively beat the ML ensemble.

Three methods are evaluated on identical data:
  * **ML ensemble**       — the existing 4-detector baseline (EWMA, HST, IF, LSTM)
  * **CEP (full)**        — primitive point rules + sequence automata
  * **CEP (automata-only)** — sequence automata with the point layer disabled
                              (ablation showing what the automaton layer adds)

Usage:
    uv run python -m ml.compare_methods
    uv run python -m ml.compare_methods --period 60d --injection-rate 0.05

Note: the OHLCV downloader uses 5-minute bars, which Yahoo only serves for the
last ~60 days — keep --period at or below 60d.
"""

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path
from statistics import mean, median

import pandas as pd

from config.logging_config import get_logger
from config.settings import settings
from cep.cep_detector import CEPDetector
from ml.backtest import (
    ScoringResult,
    _build_anomaly_reason,
    build_backtest_ensemble,
    compute_features_from_ohlcv,
    compute_metrics,
    download_raw_ohlcv,
    train_models,
    train_test_split_temporal,
)
from ml.backtest_anomalies import AnomalyInjector
from ml.ensemble import EnsembleDetector

log = get_logger("compare")


def _latency_stats(latencies_ms: list[float]) -> dict:
    if not latencies_ms:
        return {"mean_ms": 0.0, "median_ms": 0.0, "p99_ms": 0.0, "max_ms": 0.0}
    s = sorted(latencies_ms)
    p99 = s[min(len(s) - 1, int(0.99 * len(s)))]
    return {
        "mean_ms": round(mean(latencies_ms), 4),
        "median_ms": round(median(latencies_ms), 4),
        "p99_ms": round(p99, 4),
        "max_ms": round(max(latencies_ms), 4),
    }


def timed_replay(
    test_df: pd.DataFrame, train_df: pd.DataFrame, ensemble: EnsembleDetector
) -> tuple[list[ScoringResult], list[float]]:
    """Replay the test set through one method, timing each window's score()."""
    # Warm up per-ticker streaming state from training data (same as backtest).
    for ticker in train_df["ticker"].unique():
        for _, row in train_df[train_df["ticker"] == ticker].tail(50).iterrows():
            ensemble.update(row.to_dict())

    results: list[ScoringResult] = []
    latencies: list[float] = []
    for idx, row in test_df.iterrows():
        feat = row.to_dict()
        t0 = time.perf_counter()
        score, det = ensemble.score(feat)
        is_anom = ensemble.is_anomaly(score)
        latencies.append((time.perf_counter() - t0) * 1000.0)
        ensemble.update(feat)

        results.append(
            ScoringResult(
                index=int(idx),
                ticker=str(feat["ticker"]),
                timestamp=str(feat.get("timestamp", "")),
                ensemble_score=float(score),
                detector_scores={k: float(v) for k, v in det.items()},
                is_anomaly=is_anom,
                reason=_build_anomaly_reason(feat, score),
            )
        )
    return results, latencies


def build_methods(model_dir: Path) -> list[tuple[str, EnsembleDetector, float]]:
    """(name, detector, threshold) for each method under comparison."""
    return [
        ("ML ensemble", build_backtest_ensemble(model_dir), settings.ensemble_threshold),
        (
            "CEP (full)",
            EnsembleDetector([CEPDetector()], weights=[1.0], threshold=settings.cep_threshold),
            settings.cep_threshold,
        ),
        (
            "CEP (automata-only)",
            EnsembleDetector(
                [CEPDetector(point_severity=0.0)], weights=[1.0], threshold=settings.cep_threshold
            ),
            settings.cep_threshold,
        ),
    ]


def print_comparison(rows: list[dict]) -> None:
    print("\n" + "=" * 78)
    print("CEP vs ML — Detection Quality (synthetic anomaly injection)")
    print("=" * 78)
    print(f"{'Method':<22}{'Precision':>10}{'Recall':>10}{'F1':>9}{'FP-rate':>10}{'Detect':>9}")
    for r in rows:
        m = r["metrics"]
        print(
            f"{r['name']:<22}{m['precision']:>10.4f}{m['recall']:>10.4f}"
            f"{m['f1']:>9.4f}{m['false_positive_rate']:>10.4f}{m['total_detections']:>9d}"
        )

    print("\n" + "=" * 78)
    print("Latency per window (score() call), milliseconds")
    print("=" * 78)
    print(f"{'Method':<22}{'mean':>10}{'median':>10}{'p99':>10}{'max':>10}")
    for r in rows:
        lat = r["latency"]
        print(
            f"{r['name']:<22}{lat['mean_ms']:>10.4f}{lat['median_ms']:>10.4f}"
            f"{lat['p99_ms']:>10.4f}{lat['max_ms']:>10.4f}"
        )

    # Per-type recall side by side.
    types: list[str] = []
    for r in rows:
        for t in r["metrics"]["per_type_recall"]:
            if t not in types:
                types.append(t)
    print("\n" + "=" * 78)
    print("Recall by anomaly type")
    print("=" * 78)
    header = f"{'Type':<18}" + "".join(f"{r['name'][:16]:>18}" for r in rows)
    print(header)
    for t in types:
        line = f"{t:<18}"
        for r in rows:
            line += f"{r['metrics']['per_type_recall'].get(t, 0.0):>18.2f}"
        print(line)
    print()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="CEP vs ML comparison")
    # 5m interval data is only available for the last ~60 days (Yahoo limit).
    p.add_argument("--period", default="60d")
    p.add_argument("--train-ratio", type=float, default=0.7)
    p.add_argument("--injection-rate", type=float, default=0.05)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--tickers", nargs="+", default=None)
    p.add_argument("--output-dir", default="data/comparison_results")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    tickers = args.tickers or settings.tickers
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info("downloading", tickers=tickers, period=args.period)
    raw_df = download_raw_ohlcv(tickers, period=args.period)
    if raw_df.empty:
        log.error("no_data_downloaded")
        return

    features_df = pd.concat(
        [compute_features_from_ohlcv(raw_df, t, rng_seed=args.seed) for t in tickers],
        ignore_index=True,
    )
    train_df, test_df = train_test_split_temporal(features_df, train_ratio=args.train_ratio)
    log.info("split", train=len(train_df), test=len(test_df))

    # Train the ML baseline's models on this split.
    model_dir = output_dir / "models"
    train_models(train_df, model_dir)

    # Inject anomalies ONCE so every method sees identical ground truth.
    injector = AnomalyInjector(seed=args.seed, injection_rate=args.injection_rate)
    test_injected, ground_truth = injector.inject(test_df)
    log.info("injected", total=len(ground_truth))

    rows: list[dict] = []
    for name, ensemble, threshold in build_methods(model_dir):
        results, latencies = timed_replay(test_injected, train_df, ensemble)
        metrics = compute_metrics(results, ground_truth, threshold=threshold)
        rows.append(
            {"name": name, "metrics": asdict(metrics), "latency": _latency_stats(latencies)}
        )
        log.info(
            "method_done",
            method=name,
            f1=metrics.f1,
            recall=metrics.recall,
            precision=metrics.precision,
            latency_mean_ms=rows[-1]["latency"]["mean_ms"],
        )

    print_comparison(rows)

    out = {
        "config": {
            "period": args.period,
            "train_ratio": args.train_ratio,
            "injection_rate": args.injection_rate,
            "seed": args.seed,
            "tickers": tickers,
            "test_windows": len(test_injected),
            "ground_truth": len(ground_truth),
        },
        "methods": rows,
    }
    out_path = output_dir / f"comparison_{args.period}_{args.injection_rate}.json"
    out_path.write_text(json.dumps(out, indent=2))
    log.info("saved", path=str(out_path))


if __name__ == "__main__":
    main()
