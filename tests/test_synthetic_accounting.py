"""Protect population membership and distinguish cases from alert counts."""
from evaluation.run_synthetic import run_protocol


def test_negative_alerts_are_in_pooled_false_positives():
    records = []
    result = run_protocol(1, include_bootstrap=False, scenario_records=records)
    positives = [row for row in records if row['kind'] == 'positive']
    negatives = [row for row in records if row['kind'] == 'negative_control']
    assert len(positives) == 18
    assert len(negatives) == 12
    positive_alerts = sum(len(row['detections']) for row in positives)
    negative_alerts = sum(len(row['detections']) for row in negatives)
    alerting_controls = sum(bool(row['detections']) for row in negatives)
    assert (positive_alerts, negative_alerts, alerting_controls) == (21, 3, 2)
    assert result['metrics']['true_positives'] == 18
    assert result['metrics']['false_positives'] == positive_alerts + negative_alerts - 18 == 6
    assert result['negative_controls']['alerts'] == alerting_controls
