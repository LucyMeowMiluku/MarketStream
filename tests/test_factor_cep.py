import time
from datetime import timedelta

import numpy as np
import pytest

from cep.cep_detector import CEPDetector
from evaluation.synthetic_scenarios import NEGATIVE_CONTROLS, PATTERNS, generate_scenario


@pytest.mark.parametrize("pattern", PATTERNS)
def test_each_factor_pattern_completes(pattern):
    scenario = generate_scenario(pattern, seed=1, intensity="medium")
    detector = CEPDetector(cooldown_seconds=0)
    results = [
        detector.process(snapshot, detected_at=snapshot.event_time)
        for snapshot in scenario.snapshots
    ]
    assert any(
        result.is_alert
        and any(item.name == pattern and item.status == "completed" for item in result.patterns)
        for result in results
    )


@pytest.mark.parametrize("intensity", ["medium", "high"])
@pytest.mark.parametrize("control", NEGATIVE_CONTROLS)
def test_negative_controls_do_not_alert(control, intensity):
    # High intensity makes return_surprise extreme; a lone extreme price move
    # without residual confirmation is not a stock-specific dislocation.
    scenario = generate_scenario(control, seed=2, intensity=intensity)
    detector = CEPDetector(cooldown_seconds=0)
    results = [detector.process(snapshot) for snapshot in scenario.snapshots]
    assert not any(result.is_alert for result in results)


def test_warmup_and_bad_quality_suppress_completed_pattern():
    scenario = generate_scenario("stock_specific_dislocation", seed=1, intensity="medium")
    warmup = scenario.snapshots[0]
    warmup.warmup_status = "warming_up"
    result = CEPDetector().process(warmup)
    assert not result.is_alert
    assert "warm-up" in result.explanation

    degraded = generate_scenario("stock_specific_dislocation", seed=1, intensity="medium").snapshots[0]
    degraded.data_quality["flags"] = ["stale"]
    result = CEPDetector().process(degraded)
    assert not result.is_alert
    assert "data quality" in result.explanation


def test_cooldown_merges_same_ticker_pattern_direction():
    first = generate_scenario("stock_specific_dislocation", seed=1, intensity="medium")
    second = generate_scenario(
        "stock_specific_dislocation",
        seed=2,
        intensity="medium",
        start=first.ended_at + timedelta(seconds=10),
    )
    detector = CEPDetector(cooldown_seconds=300)
    one = detector.process(first.snapshots[0])
    two = detector.process(second.snapshots[0])
    assert one.is_alert
    assert not two.is_alert
    assert any(pattern.status == "merged" for pattern in two.patterns)
    assert one.dedupe_key != two.dedupe_key


def test_detection_result_is_traceable_and_human_readable():
    snapshot = generate_scenario("news_confirmed_move", seed=4, intensity="medium").snapshots
    detector = CEPDetector(cooldown_seconds=0)
    detector.process(snapshot[0])
    result = detector.process(snapshot[1])
    assert result.is_alert
    assert result.source_event_ids
    assert "news_confirmed_move" in result.explanation
    assert result.factor_evidence
    assert result.dedupe_key


def test_pattern_can_be_disabled_for_ablation():
    scenario = generate_scenario("news_confirmed_move", seed=4, intensity="medium")
    enabled = set(PATTERNS).difference({"news_confirmed_move"})
    detector = CEPDetector(cooldown_seconds=0, enabled_factor_patterns=enabled)
    results = [detector.process(snapshot) for snapshot in scenario.snapshots]
    assert not any(
        pattern.name == "news_confirmed_move"
        for result in results
        for pattern in result.patterns
    )


def test_cep_p99_below_five_milliseconds():
    scenario = generate_scenario("high_volume_no_price_move", seed=1, intensity="medium")
    detector = CEPDetector(cooldown_seconds=0)
    latencies = []
    for _ in range(1_000):
        started = time.perf_counter_ns()
        detector.process(scenario.snapshots[0])
        latencies.append((time.perf_counter_ns() - started) / 1_000_000)
    assert np.percentile(latencies, 99) <= 5.0


def test_cep_ticker_state_has_a_fixed_upper_bound():
    detector = CEPDetector(cooldown_seconds=0, max_tickers=2)
    for index, ticker in enumerate(("AAPL", "TSLA", "NVDA")):
        snapshot = generate_scenario(
            "stock_specific_dislocation",
            seed=index,
            intensity="medium",
        ).snapshots[0]
        snapshot.ticker = ticker
        detector.process(snapshot)
    assert detector.factor_state_size["tickers"] == 2
    assert detector.factor_state_size["histories"] <= 2
