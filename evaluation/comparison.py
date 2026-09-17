"""Fair event-level comparison on one shared sequence of factor snapshots."""

from __future__ import annotations

import hashlib

from cep.cep_detector import CEPDetector, PATTERN_SEVERITY
from evaluation.isolation_forest import FACTOR_COLUMNS, IsolationForestBaseline
from evaluation.metrics import DetectedEvent, GroundTruthEvent, compute_event_metrics
from processing.event_models import FactorSnapshot


def _identity(method: str, snapshot: FactorSnapshot) -> str:
    raw = f"{method}|{snapshot.ticker}|{snapshot.event_time.isoformat()}|{snapshot.cadence}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


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

    baseline, if_detections = isolation_forest_detections(
        ordered_train,
        ordered_test,
        contamination=contamination,
        random_state=random_state,
    )

    detector = CEPDetector()
    cep_detections = []
    for snapshot in ordered_test:
        result = detector.process(snapshot, detected_at=snapshot.event_time)
        completed = [item for item in result.patterns if item.status == "completed"]
        primary = max(
            completed,
            key=lambda item: PATTERN_SEVERITY.get(item.name, 0.0),
            default=None,
        )
        if result.is_alert and primary:
            cep_detections.append(
                DetectedEvent(
                    detection_id=_identity("cep", snapshot),
                    ticker=snapshot.ticker,
                    pattern=primary.name,
                    direction=primary.direction,
                    detected_at=snapshot.event_time,
                )
            )

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
        },
        "methods": {
            "factor_cep": compute_event_metrics(
                truth, cep_detections, require_pattern=False
            ).to_dict(),
            "isolation_forest": compute_event_metrics(
                truth, if_detections, require_pattern=False
            ).to_dict(),
        },
    }


def isolation_forest_detections(
    training: list[FactorSnapshot],
    testing: list[FactorSnapshot],
    *,
    contamination: float = 0.05,
    random_state: int = 42,
) -> tuple[IsolationForestBaseline, list[DetectedEvent]]:
    """Fit on one interval's baseline phase and score its evaluation phase."""

    baseline = IsolationForestBaseline(
        contamination=contamination,
        random_state=random_state,
    )
    baseline.fit(training)
    detections = []
    for snapshot in testing:
        prediction = baseline.predict(snapshot)
        if prediction.is_anomaly:
            detections.append(
                DetectedEvent(
                    detection_id=_identity("isolation_forest", snapshot),
                    ticker=snapshot.ticker,
                    pattern="point_anomaly",
                    direction=prediction.direction,
                    detected_at=snapshot.event_time,
                )
            )
    return baseline, detections
