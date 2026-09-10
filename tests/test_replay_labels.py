import json
from datetime import datetime, timedelta, timezone

import pytest

from replay.evaluator import RealReplayEvaluator
from replay.labels import LabelRegistry, freeze_registry, load_label_registry
from replay.models import ReplayRunConfig, ReviewedInterval


START = datetime(2025, 1, 6, 15, 0, tzinfo=timezone.utc)


def _interval(index: int, kind: str, ticker: str) -> ReviewedInterval:
    return ReviewedInterval(
        interval_id=f"{kind}-{index}",
        kind=kind,
        ticker=ticker,
        started_at=START + timedelta(days=index),
        ended_at=START + timedelta(days=index, hours=1),
        direction="up" if kind == "anomaly" else None,
        pattern="market_anomaly" if kind == "anomaly" else None,
        event_id=f"event-{index}" if kind == "anomaly" else None,
        evidence_urls=("https://example.com/evidence",) if kind == "anomaly" else (),
        confidence=0.9,
        approval_status="approved",
        reviewed_by="reviewer",
        reviewed_at=START,
        context_tickers=(),
    )


def _registry() -> LabelRegistry:
    tickers = ["AAPL", "TSLA", "NVDA", "QQQ", "SPY"]
    intervals = [
        _interval(index, "anomaly", tickers[index % len(tickers)]) for index in range(12)
    ]
    intervals.extend(
        _interval(index + 20, "normal", tickers[index % len(tickers)])
        for index in range(12)
    )
    return LabelRegistry(
        schema_version="marketstream-reviewed-labels-v1",
        dataset_id="reviewed-v1",
        data_kind="real_historical",
        provider="alpaca",
        feed="iex",
        timezone="America/New_York",
        frozen=True,
        frozen_at=START,
        intervals=intervals,
    )


def test_registry_requires_complete_12_plus_12_coverage():
    registry = _registry()
    registry.validate(require_frozen=True, expected_anomalies=12, expected_normals=12)
    assert len(registry.digest) == 64


def test_freeze_refuses_unapproved_interval(tmp_path):
    registry = _registry()
    value = registry.to_dict()
    value["frozen"] = False
    value["frozen_at"] = None
    value["intervals"][0]["approval_status"] = "proposed"
    value["intervals"][0]["reviewed_by"] = None
    value["intervals"][0]["reviewed_at"] = None
    source = tmp_path / "draft.json"
    source.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="independently approved"):
        freeze_registry(source, tmp_path / "frozen.json")


def test_registry_round_trip(tmp_path):
    registry = _registry()
    path = tmp_path / "labels.json"
    path.write_text(json.dumps(registry.to_dict()))
    loaded = load_label_registry(path)
    assert loaded.to_dict() == registry.to_dict()


def test_real_evaluation_refuses_incomplete_pagination_manifest(tmp_path):
    registry = _registry()
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps(registry.to_dict()))
    manifest = {
        "schema_version": "marketstream-real-replay-dataset-v1",
        "dataset_id": registry.dataset_id,
        "data_kind": "real_historical",
        "provider": "alpaca",
        "feed": "iex",
        "baseline_days": 20,
        "labels_sha256": registry.digest,
        "intervals": [
            {"interval_id": item.interval_id, "requests": [{"complete": False}]}
            for item in registry.intervals
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    config = ReplayRunConfig(
        dataset_manifest=manifest_path,
        labels_path=labels,
        output_dir=tmp_path / "runs",
    )
    with pytest.raises(ValueError, match="pagination manifest"):
        RealReplayEvaluator(config).run()
