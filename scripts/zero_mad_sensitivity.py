"""Label-free sensitivity study for zero-MAD robust-scale handling.

Runs the production quality gate, factor engine, CEP, Isolation Forest and
shared alert policy on the 2023-Q4 calibration set (see
scripts/collect_calibration_events.py) under several raw-return scale rules.
Sessions 1-20 only build the rolling 20-session baseline; sessions 21-30 are
measured, which matches the evaluator's frozen 20-session baseline per
interval.  No labels are used.  Criteria are declared in
docs/ZERO_MAD_SENSITIVITY_CN.md before the results were produced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, replace
from datetime import timedelta
from pathlib import Path

import numpy as np

from evaluation.comparison import (
    apply_shared_alert_policy,
    cep_window_detections,
    isolation_forest_detections,
)
from processing.data_quality import EventQualityGate
from processing.event_models import EventType, FactorSnapshot, MarketEvent
from processing.factor_engine import LightweightFactorEngine
from processing.factor_state import NY

BASELINE_SESSIONS = 20
GAUSSIAN_MAD = 1.4826
GAUSSIAN_MEAN_AD = 1.2533  # sqrt(pi / 2): mean absolute deviation -> sigma
TICK = 0.01  # Reg NMS minimum price increment for stocks above $1
PRIMARY = "mean_ad_tick_1"


@dataclass(frozen=True)
class Variant:
    name: str
    mean_ad: bool  # MeanAD fallback when the raw-return MAD is zero
    floor_fixed: float | None = None  # lower bound in return units
    floor_ticks: float | None = None  # lower bound in ticks / reference price
    zero_when_degenerate: bool = False  # alternative: no score without spread
    mean_ad_factors: bool = False  # exploratory: fallback in classification too
    bar_end_time: bool = False  # robustness: timestamp bars at the minute end


def _spread(values, median, mad, *, mean_ad: bool) -> tuple[float, str]:
    if mad > 0:
        return GAUSSIAN_MAD * mad, "mad"
    if mean_ad and values:
        spread = statistics.fmean(abs(value - median) for value in values)
        if spread > 0:
            return GAUSSIAN_MEAN_AD * spread, "mean_ad"
    return 0.0, "degenerate"


class VariantEngine(LightweightFactorEngine):
    def __init__(self, variant: Variant, **kwargs) -> None:
        super().__init__(**kwargs)
        self.variant = variant
        self._last_scale: dict = {}

    def _return_scale(self, series, session_date, reference_price):
        values = series.samples_before(session_date)
        median, mad, _, _ = series.summary(before=session_date)
        spread, source = _spread(values, median, mad, mean_ad=self.variant.mean_ad)
        if self.variant.floor_ticks is not None and reference_price > 0:
            floor = self.variant.floor_ticks * TICK / reference_price
        else:
            floor = self.variant.floor_fixed if self.variant.floor_fixed is not None else 1e-6
        final = max(spread, floor)
        if self.variant.zero_when_degenerate and source == "degenerate":
            final = float("inf")
        self._last_scale = {"source": source, "floor_bound": spread < floor, "mad_zero": mad == 0}
        return final

    def _factor_scale(self, series, session_date, median, mad):
        values = series.samples_before(session_date)
        spread, _ = _spread(values, median, mad, mean_ad=self.variant.mean_ad_factors)
        return max(spread, 1e-6)

    def _finalize(self, ticker, cadence, window):
        snapshot = super()._finalize(ticker, cadence, window)
        snapshot.input_summary["scale"] = dict(self._last_scale)
        return snapshot


def variants() -> list[Variant]:
    return [
        Variant("legacy_fixed_1e-06", mean_ad=False, floor_fixed=1e-6),
        Variant("fixed_1e-05", mean_ad=False, floor_fixed=1e-5),
        Variant("fixed_5e-05", mean_ad=False, floor_fixed=5e-5),
        Variant("fixed_1e-04", mean_ad=False, floor_fixed=1e-4),
        Variant("tick_1_no_mean_ad", mean_ad=False, floor_ticks=1),
        Variant("mean_ad_fixed_1e-06", mean_ad=True, floor_fixed=1e-6),
        Variant("mean_ad_tick_0.5", mean_ad=True, floor_ticks=0.5),
        Variant(PRIMARY, mean_ad=True, floor_ticks=1),
        Variant("mean_ad_tick_2", mean_ad=True, floor_ticks=2),
        Variant("mean_ad_tick_4", mean_ad=True, floor_ticks=4),
        Variant("zero_when_mad_zero", mean_ad=False, floor_ticks=1, zero_when_degenerate=True),
        Variant("mean_ad_tick_1_factors_too", mean_ad=True, floor_ticks=1, mean_ad_factors=True),
        Variant("bar_end_legacy", mean_ad=False, floor_fixed=1e-6, bar_end_time=True),
        Variant("bar_end_mean_ad_tick_1", mean_ad=True, floor_ticks=1, bar_end_time=True),
    ]


def _load_session(path: Path, bar_end_time: bool) -> list[MarketEvent]:
    events = [MarketEvent.from_dict(json.loads(line)) for line in path.read_text().splitlines()]
    if bar_end_time:
        events = [
            replace(event, event_time=event.event_time + timedelta(minutes=1))
            if event.event_type == EventType.BAR
            else event
            for event in events
        ]
        events.sort(key=lambda event: (event.event_time, event.event_id))
    return events


def _session_of(snapshot: FactorSnapshot) -> str:
    return (snapshot.window_start or snapshot.event_time).astimezone(NY).date().isoformat()


def _bucket(session: str, alert) -> list:
    minute = alert.detected_at.astimezone(NY)
    return [session, alert.ticker, alert.direction, minute.hour, minute.minute // 5]


def run_block(variant: Variant, block_dir: Path, sessions: list[str]) -> dict:
    engine = VariantEngine(variant, cadences=(10, 60, 300), min_history_days=5, baseline_days=20)
    quality = EventQualityGate()
    by_session: dict[str, list[FactorSnapshot]] = defaultdict(list)
    for session in sessions:
        for event in _load_session(block_dir / f"{session}.events.jsonl", variant.bar_end_time):
            assessed = quality.assess(event, mode="replay", now=event.event_time)
            for snapshot in engine.process(assessed):
                by_session[_session_of(snapshot)].append(snapshot)
    for snapshot in engine.flush():
        by_session[_session_of(snapshot)].append(snapshot)

    counts: Counter = Counter()
    abs_z: dict[str, list[float]] = defaultdict(list)
    detections, alert_keys = [], {"cep": [], "if": []}
    for index, session in enumerate(sessions[BASELINE_SESSIONS:], start=BASELINE_SESSIONS):
        day = sorted(by_session[session], key=lambda s: (s.event_time, s.ticker, s.cadence))
        counts["not_ready"] += sum(item.warmup_status != "ready" for item in day)
        day = [item for item in day if item.warmup_status == "ready"]
        for item in day:
            source = item.input_summary["scale"]["source"]
            atom = item.factor_states["return_surprise"]["state"] in {"elevated", "extreme"}
            for key in (f"{item.cadence}:{source}", f"all:{source}"):
                counts[f"windows:{key}"] += 1
                counts[f"atoms:{key}"] += atom
                counts[f"floor_bound:{key}"] += item.input_summary["scale"]["floor_bound"]
            abs_z[source].append(abs(item.factor_values["return_surprise"]))
        cep_windows = cep_window_detections(day)
        training_days = sessions[index - BASELINE_SESSIONS : index]
        for ticker in sorted({item.ticker for item in day}):
            training = [s for past in training_days for s in by_session[past] if s.ticker == ticker]
            scored = [item for item in day if item.ticker == ticker]
            if any(item.warmup_status == "ready" for item in training):
                _, if_windows = isolation_forest_detections(training, scored)
            else:
                counts["if_skipped_no_ready_training"] += 1
                if_windows = []
            for method, windows in (
                ("cep", [w for w in cep_windows if w.snapshot.ticker == ticker]),
                ("if", if_windows),
            ):
                alerts, outcomes = apply_shared_alert_policy(windows)
                alert_keys[method].extend(_bucket(session, alert) for alert in alerts)
                for item in windows:
                    if item.detection is None:
                        continue
                    scale = item.snapshot.input_summary["scale"]
                    detections.append({
                        "method": method,
                        "cadence": item.snapshot.cadence,
                        "pattern": item.detection.pattern,
                        "alert": outcomes[item.detection.detection_id] == "alert",
                        "source": scale["source"],
                        "floor_bound": scale["floor_bound"],
                    })
    return {
        "counts": dict(counts),
        "abs_return_surprise": dict(abs_z),
        "detections": detections,
        "alert_keys": alert_keys,
        "measured_ticker_hours": len(sessions[BASELINE_SESSIONS:]) * 5 * 1.5,
    }


def _job(args):
    variant, block_dir, sessions = args
    return variant.name, block_dir.name, run_block(variant, block_dir, sessions)


def _share(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def summarize(results: dict) -> dict:
    """Pool both blocks and evaluate the pre-declared criteria."""

    summary = {}
    keys = {}
    for name, blocks in results.items():
        counts: Counter = Counter()
        rows, hours = [], 0.0
        abs_z: dict[str, list[float]] = defaultdict(list)
        keys[name] = {"cep": set(), "if": set()}
        for value in blocks.values():
            counts.update(value["counts"])
            rows.extend(value["detections"])
            for source, values in value["abs_return_surprise"].items():
                abs_z[source].extend(values)
            hours += value["measured_ticker_hours"]
            for method in ("cep", "if"):
                keys[name][method].update(map(tuple, value["alert_keys"][method]))
        windows = {
            source: counts[f"windows:all:{source}"] for source in ("mad", "mean_ad", "degenerate")
        }
        total = sum(windows.values())
        atoms = {source: counts[f"atoms:all:{source}"] for source in windows}
        mad_rate = _share(atoms["mad"], windows["mad"])
        fallback_windows = windows["mean_ad"] + windows["degenerate"]
        fallback_rate = _share(atoms["mean_ad"] + atoms["degenerate"], fallback_windows)
        per_cadence = {
            cadence: {
                "windows": sum(counts[f"windows:{cadence}:{s}"] for s in windows),
                "mad_zero_share": _share(
                    counts[f"windows:{cadence}:mean_ad"] + counts[f"windows:{cadence}:degenerate"],
                    sum(counts[f"windows:{cadence}:{s}"] for s in windows),
                ),
                "degenerate_share": _share(
                    counts[f"windows:{cadence}:degenerate"],
                    sum(counts[f"windows:{cadence}:{s}"] for s in windows),
                ),
                "floor_bound_share": _share(
                    sum(counts[f"floor_bound:{cadence}:{s}"] for s in windows),
                    sum(counts[f"windows:{cadence}:{s}"] for s in windows),
                ),
            }
            for cadence in ("10s", "1m", "5m")
        }
        methods = {}
        for method in ("cep", "if"):
            fired = [row for row in rows if row["method"] == method]
            alerts = [row for row in fired if row["alert"]]
            methods[method] = {
                "raw_detections": len(fired),
                "policy_alerts": len(alerts),
                "policy_alerts_per_ticker_hour": len(alerts) / hours,
                "alerts_floor_bound_share": _share(sum(r["floor_bound"] for r in alerts), len(alerts)),
                "alerts_mad_zero_share": _share(sum(r["source"] != "mad" for r in alerts), len(alerts)),
                "alerts_by_pattern": dict(Counter(r["pattern"] for r in alerts)),
            }
        summary[name] = {
            "not_ready_windows": counts["not_ready"],
            "windows": total,
            "per_cadence": per_cadence,
            "return_surprise_atom_rate": {
                "mad_windows": mad_rate,
                "mad_zero_windows": fallback_rate,
                "ratio": fallback_rate / mad_rate if mad_rate and fallback_rate is not None else None,
            },
            "abs_return_surprise_by_source": {
                source: {str(q): float(np.percentile(values, q)) for q in (50, 99, 99.9, 100)}
                for source, values in abs_z.items()
                if values
            },
            "methods": methods,
            "measured_ticker_hours": hours,
        }
    for name, value in summary.items():
        for method in ("cep", "if"):
            reference, current = keys[PRIMARY][method], keys[name][method]
            union = reference | current
            value["methods"][method]["jaccard_vs_primary"] = (
                len(reference & current) / len(union) if union else 1.0
            )
            base = summary[PRIMARY]["methods"][method]["policy_alerts"]
            value["methods"][method]["alert_count_change_vs_primary"] = (
                value["methods"][method]["policy_alerts"] / base - 1 if base else None
            )
    primary = summary[PRIMARY]
    criteria = {
        "C2_floor_dominance_cep": primary["methods"]["cep"]["alerts_floor_bound_share"],
        "C2_floor_dominance_if": primary["methods"]["if"]["alerts_floor_bound_share"],
        "C3_stability": {
            name: {
                method: {
                    "count_change": summary[name]["methods"][method]["alert_count_change_vs_primary"],
                    "jaccard": summary[name]["methods"][method]["jaccard_vs_primary"],
                }
                for method in ("cep", "if")
            }
            for name in ("mean_ad_tick_0.5", "mean_ad_tick_2")
        },
        "C4_atom_rate_ratio": primary["return_surprise_atom_rate"]["ratio"],
    }
    passed = {
        "C2": all(
            value is None or value <= 0.05
            for value in (criteria["C2_floor_dominance_cep"], criteria["C2_floor_dominance_if"])
        ),
        "C3": all(
            item["count_change"] is not None
            and abs(item["count_change"]) <= 0.10
            and item["jaccard"] >= 0.85
            for methods in criteria["C3_stability"].values()
            for item in methods.values()
        ),
        "C4": criteria["C4_atom_rate_ratio"] is None or criteria["C4_atom_rate_ratio"] <= 2.0,
    }
    return {"variants": summary, "criteria": criteria, "passed": passed}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/calibration/zero_mad_2023q4"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    manifest_path = args.data / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    sessions = manifest["sessions"]
    jobs = [(v, args.data / block, sessions) for v in variants() for block in manifest["blocks"]]
    results: dict = defaultdict(dict)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for name, block, value in pool.map(_job, jobs):
            results[name][block] = value
            print(f"done {name} {block}", flush=True)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(json.dumps({
        "calibration_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "variants": {v.name: asdict(v) for v in variants()},
        "primary": PRIMARY,
        **summarize(results),
    }, indent=2) + "\n")
    (args.output / "per_block.json").write_text(json.dumps({
        name: {block: {k: v for k, v in value.items() if k not in {"detections", "abs_return_surprise"}}
               for block, value in blocks.items()}
        for name, blocks in results.items()
    }) + "\n")


if __name__ == "__main__":
    main()
