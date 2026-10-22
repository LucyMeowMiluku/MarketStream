"""Protect population membership and distinguish cases from alert counts."""
import evaluation.run_synthetic as synthetic
from evaluation.run_synthetic import run_protocol
from evaluation.synthetic_scenarios import generate_scenario


def _alerting_orderly_move(name, **kwargs):
    scenario = generate_scenario(name, **kwargs)
    if name == "orderly_market_move":
        # Add a matching residual so this control fires once per ticker and the
        # accounting below is exercised independently of detector behaviour.
        for snapshot in scenario.snapshots:
            price = snapshot.factor_states["return_surprise"]
            snapshot.factor_values["market_residual"] = snapshot.factor_values["return_surprise"]
            snapshot.factor_states["market_residual"].update(
                state=price["state"], direction=price["direction"]
            )
    return scenario


def test_negative_alerts_are_in_pooled_false_positives(monkeypatch):
    monkeypatch.setattr(synthetic, "generate_scenario", _alerting_orderly_move)
    records = []
    result = run_protocol(1, include_bootstrap=False, scenario_records=records)
    positives = [row for row in records if row['kind'] == 'positive']
    negatives = [row for row in records if row['kind'] == 'negative_control']
    assert len(positives) == 18
    assert len(negatives) == 12
    positive_alerts = sum(len(row['detections']) for row in positives)
    negative_alerts = sum(len(row['detections']) for row in negatives)
    alerting_controls = sum(bool(row['detections']) for row in negatives)
    assert (positive_alerts, negative_alerts, alerting_controls) == (18, 6, 3)
    assert result['metrics']['true_positives'] == 18
    assert result['metrics']['false_positives'] == positive_alerts + negative_alerts - 18 == 6
    assert result['negative_controls']['alerts'] == alerting_controls
