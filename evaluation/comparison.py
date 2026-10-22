"""Fair event-level comparison on one shared sequence of factor snapshots.

Both methods first produce raw per-window detections.  One shared alert
policy (warm-up and data-quality gate, then a cooldown keyed by ticker and
direction) turns raw detections into alerts, so post-processing differences
do not drive the precision comparison.  Raw detections are kept as well.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta

from cep.cep_detector import CEPDetector, PATTERN_SEVERITY
from evaluation.isolation_forest import (
    FACTOR_COLUMNS,
    BaselinePrediction,
    IsolationForestBaseline,
)
from evaluation.metrics import DetectedEvent, GroundTruthEvent, compute_event_metrics
from processing.event_models import CRITICAL_QUALITY_FLAGS, FactorSnapshot

SHARED_ALERT_COOLDOWN = timedelta(minutes=5)


@dataclass(frozen=True, slots=True)
class WindowDetection:
    """One method's raw output for one scored factor window."""

    snapshot: FactorSnapshot
    detection: DetectedEvent | None  # None when the method did not fire
    score: float  # higher means more anomalous (CEP severity, -IF decision)


def _identity(method: str, snapshot: FactorSnapshot) -> str:
    raw = f"{method}|{snapshot.ticker}|{snapshot.event_time.isoformat()}|{snapshot.cadence}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def apply_shared_alert_policy(
    windows: list[WindowDetection],
    *,
    cooldown: timedelta = SHARED_ALERT_COOLDOWN,
) -> tuple[list[DetectedEvent], dict[str, str]]:
    """Apply the same post-processing to any method's raw detections.

    Returns the emitted alerts and, for every fired window, its policy outcome:
    ``alert``, ``warmup``, ``quality`` or ``cooldown``.  Only emitted alerts
    start a cooldown, matching the production CEP rule.
    """

    alerts: list[DetectedEvent] = []
    outcomes: dict[str, str] = {}
    cooldown_until: dict[tuple[str, str], datetime] = {}
    fired = sorted(
        (item for item in windows if item.detection is not None),
        key=lambda item: (item.detection.detected_at, item.detection.detection_id),
    )
    for item in fired:
        detection = item.detection
        if item.snapshot.warmup_status != "ready":
            outcomes[detection.detection_id] = "warmup"
            continue
        if CRITICAL_QUALITY_FLAGS.intersection(item.snapshot.data_quality.get("flags", [])):
            outcomes[detection.detection_id] = "quality"
            continue
        key = (detection.ticker, detection.direction)
        if key in cooldown_until and detection.detected_at < cooldown_until[key]:
            outcomes[detection.detection_id] = "cooldown"
            continue
        cooldown_until[key] = detection.detected_at + cooldown
        outcomes[detection.detection_id] = "alert"
        alerts.append(detection)
    return alerts, outcomes


def raw_detections(windows: list[WindowDetection]) -> list[DetectedEvent]:
    return [item.detection for item in windows if item.detection is not None]


def cep_window_detections(
    snapshots: list[FactorSnapshot],
    detection_id=lambda snapshot, result: _identity("cep", snapshot),
) -> list[WindowDetection]:
    """Run CEP without its own cooldown and record every completed pattern."""

    detector = CEPDetector(cooldown_seconds=0)
    windows = []
    for snapshot in snapshots:
        result = detector.process(snapshot, detected_at=snapshot.event_time)
        primary = max(
            (item for item in result.patterns if item.status == "completed"),
            key=lambda item: PATTERN_SEVERITY.get(item.name, 0.0),
            default=None,
        )
        detection = None
        if primary is not None:
            detection = DetectedEvent(
                detection_id=detection_id(snapshot, result),
                ticker=snapshot.ticker,
                pattern=primary.name,
                direction=primary.direction,
                detected_at=snapshot.event_time,
            )
        windows.append(WindowDetection(snapshot, detection, -result.score))
    return windows


def compare_detectors(
    training: list[FactorSnapshot],
    testing: list[FactorSnapshot],
    truth: list[GroundTruthEvent],
    *,
    labels_frozen: bool,
    contamination: float = 0.05,
    random_state: int = 42,
) -> dict:
    """Compare CEP and IF only when the reviewed ground truth is frozen."""

    if not labels_frozen:
        raise ValueError("formal comparison requires independently reviewed frozen labels")
    if not testing:
        raise ValueError("comparison requires non-empty test snapshots")

    ordered_train = sorted(training, key=lambda item: item.event_time)
    ordered_test = sorted(testing, key=lambda item: item.event_time)
    if ordered_train and ordered_train[-1].event_time >= ordered_test[0].event_time:
        raise ValueError("training snapshots must end before the test interval")

    baseline, if_windows = isolation_forest_detections(
        ordered_train,
        ordered_test,
        contamination=contamination,
        random_state=random_state,
    )
    cep_windows = cep_window_detections(ordered_test)
    windows = {"factor_cep": cep_windows, "isolation_forest": if_windows}

    return {
        "data_kind": "real_historical",
        "labels_frozen": True,
        "feature_contract": list(FACTOR_COLUMNS),
        "config": {
            "contamination": contamination,
            "random_state": random_state,
            "training_snapshots": len(ordered_train),
            "testing_snapshots": len(ordered_test),
            "training_ended_at": baseline.training_ended_at.isoformat(),
            "alert_policy": shared_alert_policy_description(),
        },
        "methods": {
            method: compute_event_metrics(
                truth, apply_shared_alert_policy(items)[0], require_pattern=False
            ).to_dict()
            for method, items in windows.items()
        },
        "raw_per_window_methods": {
            method: compute_event_metrics(
                truth, raw_detections(items), require_pattern=False
            ).to_dict()
            for method, items in windows.items()
        },
    }


def shared_alert_policy_description() -> dict:
    return {
        "gates": ["warmup_status == ready", f"no {sorted(CRITICAL_QUALITY_FLAGS)} flag"],
        "cooldown_seconds": int(SHARED_ALERT_COOLDOWN.total_seconds()),
        "cooldown_key": ["ticker", "direction"],
        "cooldown_started_by": "emitted alerts only",
        "applies_to": ["factor_cep", "isolation_forest"],
    }


def isolation_forest_detections(
    training: list[FactorSnapshot],
    testing: list[FactorSnapshot],
    *,
    contamination: float = 0.05,
    random_state: int = 42,
) -> tuple[IsolationForestBaseline, list[WindowDetection]]:
    """Fit on one interval's baseline phase and score its evaluation phase.

    Warm-up snapshots are excluded from fitting: their factor values are
    computed against immature baselines and would distort the scaler.
    """

    ready = [snapshot for snapshot in training if snapshot.warmup_status == "ready"]
    if not ready:
        raise ValueError("Isolation Forest requires post-warm-up training snapshots")
    baseline = IsolationForestBaseline(
        contamination=contamination,
        random_state=random_state,
    )
    baseline.fit(ready)
    windows = []
    for snapshot in testing:
        prediction: BaselinePrediction = baseline.predict(snapshot)
        detection = None
        if prediction.is_anomaly:
            detection = DetectedEvent(
                detection_id=_identity("isolation_forest", snapshot),
                ticker=snapshot.ticker,
                pattern="point_anomaly",
                direction=prediction.direction,
                detected_at=snapshot.event_time,
            )
        windows.append(WindowDetection(snapshot, detection, -prediction.score))
    return baseline, windows
