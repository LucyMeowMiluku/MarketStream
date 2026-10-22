from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from evaluation.comparison import compare_detectors, isolation_forest_detections
from evaluation.isolation_forest import FACTOR_COLUMNS, IsolationForestBaseline
from evaluation.metrics import GroundTruthEvent
from processing.event_models import FACTOR_GROUPS, FactorSnapshot


START = datetime(2025, 1, 1, 15, 0, tzinfo=timezone.utc)


def _snapshot(index: int, *, anomalous: bool = False) -> FactorSnapshot:
    event_time = START + timedelta(seconds=index * 10)
    values = {name: float(index % 3) / 100 for name in FACTOR_COLUMNS}
    states = {
        name: {
            "group": group,
            "state": "normal",
            "direction": "up",
            "robust_z": 0.0,
        }
        for name, group in FACTOR_GROUPS.items()
    }
    if anomalous:
        values["return_surprise"] = 9.0
        values["market_residual"] = 9.0
        for name in ("return_surprise", "market_residual"):
            states[name].update(state="extreme", robust_z=9.0)
    return FactorSnapshot(
        ticker="AAPL",
        event_time=event_time,
        window_start=event_time - timedelta(seconds=10),
        cadence="10s",
        factor_values=values,
        factor_states=states,
        baseline_version="frozen-test",
        data_quality={"status": "good", "flags": []},
        warmup_status="ready",
        source_event_ids=[f"event-{index}"],
    )


def test_baseline_fits_once_and_prediction_does_not_update_scaler():
    training = [_snapshot(index) for index in range(30)]
    baseline = IsolationForestBaseline(random_state=42)
    baseline.fit(training)
    before = baseline._scaler.mean_.copy()
    baseline.predict(_snapshot(40, anomalous=True))
    assert np.array_equal(before, baseline._scaler.mean_)
    assert baseline.training_ended_at == training[-1].event_time


def test_formal_comparison_rejects_unfrozen_labels():
    with pytest.raises(ValueError, match="frozen labels"):
        compare_detectors(
            [_snapshot(index) for index in range(30)],
            [_snapshot(40, anomalous=True)],
            [],
            labels_frozen=False,
        )


def test_both_methods_share_the_same_test_snapshots_and_event_metrics():
    training = [_snapshot(index) for index in range(30)]
    testing = [_snapshot(40, anomalous=True), _snapshot(41)]
    truth = [
        GroundTruthEvent(
            event_id="truth-1",
            ticker="AAPL",
            pattern="market_anomaly",
            direction="up",
            started_at=testing[0].event_time,
            ended_at=testing[-1].event_time,
        )
    ]
    result = compare_detectors(training, testing, truth, labels_frozen=True)
    assert result["config"]["testing_snapshots"] == 2
    assert set(result["methods"]) == {"factor_cep", "isolation_forest"}
    assert result["feature_contract"] == list(FACTOR_COLUMNS)


def test_warmup_snapshots_are_excluded_from_isolation_forest_fit():
    from dataclasses import replace

    ready = [_snapshot(index) for index in range(30)]
    # Warm-up factor values are computed against immature baselines.
    warming = [
        replace(_snapshot(100 + index, anomalous=True), warmup_status="warming_up")
        for index in range(30)
    ]
    baseline, _ = isolation_forest_detections(warming + ready, [_snapshot(200)])
    reference = IsolationForestBaseline(random_state=42)
    reference.fit(ready)
    assert np.array_equal(baseline._scaler.mean_, reference._scaler.mean_)
    with pytest.raises(ValueError, match="post-warm-up"):
        isolation_forest_detections(warming, [_snapshot(200)])


def test_shared_alert_policy_gates_then_cools_down_by_ticker_and_direction():
    from dataclasses import replace

    from evaluation.comparison import WindowDetection, apply_shared_alert_policy
    from evaluation.metrics import DetectedEvent

    def window(index, direction="up", flags=()):
        snapshot = _snapshot(index)
        snapshot.data_quality = {"status": "good", "flags": list(flags)}
        detection = DetectedEvent(
            detection_id=f"d{index}-{direction}",
            ticker="AAPL",
            pattern="any",
            direction=direction,
            detected_at=snapshot.event_time,
        )
        return WindowDetection(snapshot, detection, 1.0)

    windows = [
        window(0, flags=("stale",)),  # gated, does not start a cooldown
        window(1),  # alert at t=10s
        window(2),  # same ticker/direction inside 5 minutes
        window(3, direction="down"),  # other direction has its own cooldown
        window(32),  # t=320s: cooldown from t=10s has expired
        WindowDetection(_snapshot(40), None, 0.0),  # did not fire
    ]
    warming = window(41)
    windows.append(replace(warming, snapshot=replace(warming.snapshot, warmup_status="warming_up")))
    alerts, outcomes = apply_shared_alert_policy(windows)
    assert [item.detection_id for item in alerts] == ["d1-up", "d3-down", "d32-up"]
    assert outcomes == {
        "d0-up": "quality",
        "d1-up": "alert",
        "d2-up": "cooldown",
        "d3-down": "alert",
        "d32-up": "alert",
        "d41-up": "warmup",
    }


def test_comparison_reports_policy_and_raw_per_window_metrics():
    training = [_snapshot(index) for index in range(30)]
    testing = [_snapshot(40 + index, anomalous=True) for index in range(3)]
    result = compare_detectors(training, testing, [], labels_frozen=True)
    assert set(result["raw_per_window_methods"]) == set(result["methods"])
    assert result["config"]["alert_policy"]["cooldown_key"] == ["ticker", "direction"]
    raw_cep = result["raw_per_window_methods"]["factor_cep"]["false_positives"]
    policy_cep = result["methods"]["factor_cep"]["false_positives"]
    # Three consecutive dislocation windows fire three times but alert once.
    assert (raw_cep, policy_cep) == (3, 1)
