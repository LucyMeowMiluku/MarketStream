from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from evaluation.comparison import compare_detectors
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
