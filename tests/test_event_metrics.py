from datetime import datetime, timedelta, timezone

from evaluation.metrics import (
    DetectedEvent,
    GroundTruthEvent,
    bootstrap_confidence_intervals,
    chronological_split,
    compute_event_metrics,
    match_events,
)


START = datetime(2025, 1, 6, 15, 0, tzinfo=timezone.utc)


def _truth(event_id: str, seconds: int = 0):
    start = START + timedelta(seconds=seconds)
    return GroundTruthEvent(event_id, "AAPL", "flash_reversal", "down", start, start + timedelta(seconds=30))


def _detection(event_id: str, seconds: int):
    return DetectedEvent(event_id, "AAPL", "flash_reversal", "down", START + timedelta(seconds=seconds))


def test_forward_matching_rejects_early_detection():
    matches, false_positives, missed = match_events([_truth("truth")], [_detection("early", -1)])
    assert not matches
    assert len(false_positives) == 1
    assert len(missed) == 1


def test_one_to_one_matching_and_metrics():
    truth = [_truth("one"), _truth("two", 60)]
    detections = [_detection("d1", 10), _detection("d2", 15), _detection("d3", 70)]
    metrics = compute_event_metrics(
        truth,
        detections,
        observation_start=START,
        observation_end=START + timedelta(hours=1),
    )
    assert metrics.true_positives == 2
    assert metrics.false_positives == 1
    assert metrics.precision == 2 / 3
    assert metrics.recall == 1.0
    assert metrics.delay_p50_seconds == 10.0


def test_end_to_end_percentiles_and_bootstrap_ci():
    detected = DetectedEvent(
        "d1",
        "AAPL",
        "flash_reversal",
        "down",
        START + timedelta(seconds=5),
        received_at=START,
        persisted_at=START + timedelta(seconds=2),
    )
    metrics = compute_event_metrics([_truth("one")], [detected])
    assert metrics.end_to_end_p95_seconds == 2.0
    intervals = bootstrap_confidence_intervals([_truth("one")], [detected], samples=100)
    assert intervals["f1"] == (1.0, 1.0)


def test_chronological_split_is_60_20_20():
    train, validation, test = chronological_split(list(range(10)))
    assert train == list(range(6))
    assert validation == [6, 7]
    assert test == [8, 9]
