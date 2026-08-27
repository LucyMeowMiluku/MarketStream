"""Twenty-seed, three-intensity evaluation for factor CEP and controls."""

from __future__ import annotations

import argparse
import copy
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from cep.cep_detector import CEPDetector
from ml.event_metrics import (
    DetectedEvent,
    GroundTruthEvent,
    bootstrap_confidence_intervals,
    compute_event_metrics,
)
from ml.sequence_anomalies import INTENSITY_Z, NEGATIVE_CONTROLS, PATTERNS, generate_scenario
from processing.event_models import FACTOR_GROUPS


def run_protocol(
    seeds: int = 20,
    *,
    disabled_groups: frozenset[str] = frozenset(),
    disabled_patterns: frozenset[str] = frozenset(),
    include_bootstrap: bool = True,
) -> dict:
    truth: list[GroundTruthEvent] = []
    detections: list[DetectedEvent] = []
    latencies_ms: list[float] = []
    controls = 0
    control_alerts = 0
    scenario_index = 0
    for seed in range(seeds):
        for intensity in INTENSITY_Z:
            for name in PATTERNS + NEGATIVE_CONTROLS:
                scenario = generate_scenario(
                    name,
                    seed=seed,
                    intensity=intensity,
                    start=datetime(2025, 1, 6, 14, 30, tzinfo=timezone.utc)
                    + timedelta(minutes=10 * scenario_index),
                )
                scenario_index += 1
                detector = CEPDetector(
                    cooldown_seconds=0,
                    enabled_factor_patterns=set(PATTERNS).difference(disabled_patterns),
                )
                scenario_detections = []
                for snapshot in scenario.snapshots:
                    evaluated = copy.deepcopy(snapshot)
                    for factor, group in FACTOR_GROUPS.items():
                        if group in disabled_groups:
                            evaluated.factor_values[factor] = 0.0
                            evaluated.factor_states[factor].update(
                                state="normal",
                                direction="up",
                                robust_z=0.0,
                            )
                    started = time.perf_counter_ns()
                    result = detector.process(evaluated, detected_at=evaluated.event_time)
                    latencies_ms.append((time.perf_counter_ns() - started) / 1_000_000)
                    if result.is_alert:
                        primary_name = detector.last_match(result.ticker)
                        primary = next(
                            (
                                pattern
                                for pattern in result.patterns
                                if pattern.status == "completed" and pattern.name == primary_name
                            ),
                            None,
                        )
                        if primary is not None:
                            scenario_detections.append(
                                DetectedEvent(
                                    detection_id=result.dedupe_key or f"{name}:{seed}:{intensity}",
                                    ticker=result.ticker,
                                    pattern=primary.name,
                                    direction=primary.direction,
                                    detected_at=result.event_time,
                                )
                            )
                if scenario.expected_pattern:
                    ticker = scenario.snapshots[-1].ticker
                    truth.append(
                        GroundTruthEvent(
                            event_id=f"{name}:{seed}:{intensity}",
                            ticker=ticker,
                            pattern=name,
                            direction=scenario.expected_direction or "up",
                            started_at=scenario.started_at,
                            ended_at=scenario.ended_at,
                        )
                    )
                else:
                    controls += 1
                    control_alerts += bool(scenario_detections)
                detections.extend(scenario_detections)
    metrics = compute_event_metrics(truth, detections)
    latency = {
        "p50_ms": float(np.percentile(latencies_ms, 50)),
        "p95_ms": float(np.percentile(latencies_ms, 95)),
        "p99_ms": float(np.percentile(latencies_ms, 99)),
    }
    result = {
        "data_kind": "synthetic",
        "ground_truth_kind": "generated_factor_sequences",
        "metric_scope": "pipeline_validation_only",
        "protocol": {
            "seeds": seeds,
            "intensities": list(INTENSITY_Z),
            "patterns": list(PATTERNS),
            "disabled_groups": sorted(disabled_groups),
            "disabled_patterns": sorted(disabled_patterns),
        },
        "metrics": metrics.to_dict(),
        "cep_latency": latency,
        "negative_controls": {
            "total": controls,
            "alerts": control_alerts,
            "false_alert_rate": control_alerts / controls if controls else 0.0,
        },
    }
    if include_bootstrap:
        result["bootstrap_95_ci"] = bootstrap_confidence_intervals(truth, detections)
    return result


def run_evaluation_suite(seeds: int = 20) -> dict:
    result = run_protocol(seeds)
    ablations = {}
    for group in sorted(set(FACTOR_GROUPS.values())):
        ablation = run_protocol(
            seeds,
            disabled_groups=frozenset({group}),
            include_bootstrap=False,
        )
        ablations[f"without_group:{group}"] = {
            "metrics": ablation["metrics"],
            "negative_controls": ablation["negative_controls"],
        }
    microstructure = run_protocol(
        seeds,
        disabled_groups=frozenset({"activity", "liquidity"}),
        include_bootstrap=False,
    )
    ablations["without_microstructure"] = {
        "metrics": microstructure["metrics"],
        "negative_controls": microstructure["negative_controls"],
    }
    for pattern in PATTERNS:
        ablation = run_protocol(
            seeds,
            disabled_patterns=frozenset({pattern}),
            include_bootstrap=False,
        )
        ablations[f"without_pattern:{pattern}"] = {
            "metrics": ablation["metrics"],
            "negative_controls": ablation["negative_controls"],
        }
    result["ablations"] = ablations
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate factor CEP protocol")
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--output", type=Path, default=Path("data/evaluation/factor_cep.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_evaluation_suite(args.seeds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
