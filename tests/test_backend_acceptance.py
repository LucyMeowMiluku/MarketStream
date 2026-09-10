from datetime import datetime, timedelta, timezone

from ml.backend_acceptance import analyze_alerts


NOW = datetime(2025, 1, 6, 15, 0, tzinfo=timezone.utc)


def test_acceptance_report_measures_latency_duplicates_and_traceability():
    alerts = [
        {
            "detected_at": NOW,
            "ticker": "AAPL",
            "pattern_name": "flash_reversal",
            "direction": "down",
            "trigger_event_ids": ["one"],
            "factor_found": True,
            "raw_events_found": True,
            "data_quality": {
                "mode": "live",
                "last_received_at": (NOW - timedelta(seconds=2)).isoformat(),
            },
        },
        {
            "detected_at": NOW + timedelta(seconds=10),
            "ticker": "AAPL",
            "pattern_name": "flash_reversal",
            "direction": "down",
            "trigger_event_ids": ["two"],
            "factor_found": True,
            "raw_events_found": True,
            "data_quality": {
                "mode": "live",
                "last_received_at": (NOW + timedelta(seconds=7)).isoformat(),
            },
        },
    ]
    report = analyze_alerts(alerts, hours=1, cooldown_seconds=300)
    assert report["receipt_to_persistence_seconds"]["p95"] > 2
    assert report["duplicate_alert_rate"] == 0.5
    assert report["traceability_rate"] == 1.0
    assert not report["gates"]["duplicate_rate_le_5pct"]
