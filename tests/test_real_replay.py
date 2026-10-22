import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from replay.evaluator import RealReplayEvaluator
from replay.labels import LabelRegistry
from replay.models import ReplayRunConfig, ReviewedInterval, file_sha256
from processing.event_models import MarketEvent


START = datetime(2025, 1, 6, 15, 0, tzinfo=timezone.utc)


def _write_events(path: Path, *events: MarketEvent) -> None:
    path.write_text("".join(json.dumps(event.to_dict()) + "\n" for event in events))


def _trade(event_id: str, ticker: str, when: datetime, dataset_id: str, interval_id: str, phase: str):
    return MarketEvent.create(
        event_id=event_id,
        source="alpaca",
        feed="iex",
        event_type="trade",
        ticker=ticker,
        event_time=when,
        received_at=when,
        trade={"price": 100.0, "size": 10},
        dataset_id=dataset_id,
        mode="replay_real",
        provenance={"interval_id": interval_id, "phase": phase},
    )


def test_strict_real_replay_writes_recomputable_offline_artifacts(tmp_path):
    dataset_id = "reviewed-real-v1"
    tickers = ["AAPL", "TSLA", "NVDA", "QQQ", "SPY"]
    intervals = []
    manifest_intervals = []
    for index in range(24):
        kind = "anomaly" if index < 12 else "normal"
        ticker = tickers[index % len(tickers)]
        context = "SPY" if ticker != "SPY" else "QQQ"
        start = START + timedelta(days=index * 7)
        interval_id = f"{kind}-{index:02d}"
        interval = ReviewedInterval(
            interval_id=interval_id,
            kind=kind,
            ticker=ticker,
            started_at=start,
            ended_at=start + timedelta(minutes=1),
            direction="up" if kind == "anomaly" else None,
            pattern="market_anomaly" if kind == "anomaly" else None,
            event_id=f"event-{index:02d}" if kind == "anomaly" else None,
            evidence_urls=("https://example.com/evidence",) if kind == "anomaly" else (),
            confidence=0.9,
            approval_status="approved",
            reviewed_by="reviewer",
            reviewed_at=START,
            context_tickers=(context,),
        )
        intervals.append(interval)
        interval_dir = tmp_path / "dataset" / interval_id
        interval_dir.mkdir(parents=True)
        baseline_path = interval_dir / "baseline.jsonl"
        evaluation_path = interval_dir / "evaluation.jsonl"
        local_start = start.astimezone(ZoneInfo("America/New_York"))
        # return_surprise needs one prior raw return before it is observed and
        # then one day of its own history; a third session leaves post-warm-up
        # snapshots for fitting Isolation Forest.
        baseline_times = [
            datetime.combine(
                local_start.date() - timedelta(days=days), local_start.timetz()
            ).astimezone(timezone.utc)
            for days in (21, 14, 7)
        ]
        _write_events(
            baseline_path,
            *(
                _trade(
                    f"alpaca-baseline-{index}-{position}-{symbol}",
                    symbol,
                    baseline_time + timedelta(seconds=offset),
                    dataset_id,
                    interval_id,
                    "baseline",
                )
                for position, baseline_time in enumerate(baseline_times)
                for offset, symbol in enumerate((ticker, context))
            ),
        )
        _write_events(
            evaluation_path,
            *(
                _trade(
                    f"alpaca-evaluation-{index}-{symbol}",
                    symbol,
                    start + timedelta(seconds=offset),
                    dataset_id,
                    interval_id,
                    "evaluation",
                )
                for offset, symbol in enumerate((ticker, context))
            ),
        )
        manifest_intervals.append(
            {
                "interval_id": interval_id,
                "baseline": {
                    "path": str(baseline_path),
                    "sha256": file_sha256(baseline_path),
                    "events": 6,
                },
                "evaluation": {
                    "path": str(evaluation_path),
                    "sha256": file_sha256(evaluation_path),
                    "events": 2,
                },
                "requests": [{"complete": True}],
            }
        )
    registry = LabelRegistry(
        schema_version="marketstream-reviewed-labels-v1",
        dataset_id=dataset_id,
        data_kind="real_historical",
        provider="alpaca",
        feed="iex",
        timezone="America/New_York",
        frozen=True,
        frozen_at=START,
        intervals=intervals,
    )
    labels_path = tmp_path / "labels.json"
    labels_path.write_text(json.dumps(registry.to_dict()))
    manifest = {
        "schema_version": "marketstream-real-replay-dataset-v1",
        "dataset_id": dataset_id,
        "data_kind": "real_historical",
        "provider": "alpaca",
        "feed": "iex",
        "coverage": "Alpaca IEX only; not consolidated SIP",
        "labels_sha256": registry.digest,
        "baseline_days": 1,
        "intervals": manifest_intervals,
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    config = ReplayRunConfig(
        dataset_manifest=manifest_path,
        labels_path=labels_path,
        output_dir=tmp_path / "runs",
        run_id="test-real-run",
        cadences=(10,),
        min_history_days=1,
        baseline_days=1,
        bootstrap_samples=50,
    )
    result = RealReplayEvaluator(config).run()
    assert result["counts"]["reviewed_intervals"] == 24
    assert result["metrics"]["false_negatives"] == 12
    assert result["auxiliary"]["accuracy_reported"] is False
    for run in result["interval_runs"]:
        # Context-ticker snapshots feed features but are never scored.
        assert 0 < run["scored_snapshots"] < run["snapshots"]
    for artifact in result["artifacts"].values():
        assert Path(artifact).exists()
    html = Path(result["artifacts"]["html"]).read_text()
    assert "REAL HISTORICAL REPLAY" in html
    assert "<script src=" not in html
    assert '<link rel="icon" href="data:,">' in html
    assert "window.__MARKETSTREAM_REPORT_READY__=true" in html
    assert "Ground truth" in html
    assert "name:'News'" in html
    assert all(interval.interval_id in html for interval in intervals)
