# =================================================================================
# function：使用真实的 Alpaca IEX 事件，确定性复用质量gate、factor engine和 CEP
# 贡献：provenance/checksum 检查、baseline 冻结、追溯统计和评测tools
# 参考：严格时间切分与无偏时序异常评测原则来自于现有的公开研究[R08][R09][R10]
# 关键设计：训练基线严格早于评测区间；测试期间阈值状态不可变化。
# 需要解决的问题：数据leak、合成数据替代真实数据、标签变化和replay结果不可复现
# 解决方法：校验来源与哈希，分开 baseline/evaluation，冻结阈值，并输出完整 trace 和运行明细
# ==================================================================================
"""
历史replay需要拿真实的历史数据进行测试,在测试之前还需要确定tags是否一致和被冻结,
还需要保证未来数据并没有提前泄露给test,baseline最后一条早于评测区间的开头,跑完之后baseline未被修改

Deterministic real-market replay with strict label and leakage gates."""

from __future__ import annotations

import argparse
import json
from collections import Counter, OrderedDict
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

from cep.cep_detector import CEPDetector, PATTERN_SEVERITY
from evaluation.comparison import isolation_forest_detections
from evaluation.metrics import (
    DetectedEvent,
    GroundTruthEvent,
    bootstrap_confidence_intervals,
    compute_event_metrics,
    match_events,
)
from processing.data_quality import EventQualityGate
from processing.event_models import FACTOR_GROUPS, DetectionResult, FactorSnapshot
from processing.factor_engine import LightweightFactorEngine
from replay.html_report import write_replay_html
from replay.models import ReplayRunConfig, ReplayStep, canonical_sha256, file_sha256
from replay.validation import iter_events, resolve_artifact, validate_replay_inputs


def _primary_pattern(result: DetectionResult):
    completed = [item for item in result.patterns if item.status == "completed"]
    return max(
        completed, key=lambda item: PATTERN_SEVERITY.get(item.name, 0.0), default=None
    )


def _detection_id(interval_id: str, result: DetectionResult) -> str:
    # 优先使用生产 dedupe_key；没有时再根据完整结果生成稳定后缀
    suffix = result.dedupe_key or canonical_sha256(result.to_dict())[:24]
    return f"{interval_id}:{result.cadence}:{result.event_time.isoformat()}:{suffix}"


def _remember_event(
    recent: OrderedDict[str, None], event_id: str, limit: int = 200_000
) -> None:
    # 目标：验证 FactorSnapshot 引用的原始事件 ID 是否能够被解析
    # 关键设计：只保存有限数量的近期 ID，不保存完整事件，使长时间 replay 的内存有上限
    recent[event_id] = None
    recent.move_to_end(event_id)
    if len(recent) > limit:
        recent.popitem(last=False)


def _threshold_state_hash(state: dict[str, Any]) -> str:
    return canonical_sha256(
        {
            "baselines": state.get("baselines", []),
            "trading_days": state.get("trading_days", {}),
        }
    )


class RealReplayEvaluator:
    def __init__(self, config: ReplayRunConfig) -> None:
        self.config = config

    def _validate_inputs(self):
        return validate_replay_inputs(self.config)

    def _train_baseline(
        self,
        path: Path,
        interval_start,
        *,
        dataset_id: str,
        interval_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any], list[FactorSnapshot]]:
        # 目标：只用事件发生前的历史数据建立正常 baseline
        # 关键设计：复用生产质量门和因子引擎，但训练期不运行 CEP，也不使用目标区间标签调参
        quality = EventQualityGate()
        engine = LightweightFactorEngine(
            cadences=self.config.cadences,
            min_history_days=self.config.min_history_days,
            baseline_days=self.config.baseline_days,
        )
        counts: Counter[str] = Counter()  # 各事件类型输入数量
        training_snapshots: list[FactorSnapshot] = []
        maximum = None  # baseline 中最后一个事件时间
        for event in iter_events(path):
            # 解决的问题：合成、soak 或其他区间的数据不能被混入真实 baseline。
            # 解决方法：逐条核对 source、mode、dataset、interval 和 phase，并拒绝 synthetic/soak ID。
            if event.source != "alpaca" or event.mode != "replay_real":
                raise ValueError(
                    f"baseline contains non-real source: {event.source}/{event.mode}"
                )
            if event.dataset_id != dataset_id:
                raise ValueError(
                    "baseline event dataset_id does not match the manifest"
                )
            if event.provenance.get("interval_id") != interval_id:
                raise ValueError(
                    "baseline event interval provenance does not match the manifest"
                )
            if event.provenance.get("phase") != "baseline":
                raise ValueError("baseline event is missing baseline phase provenance")
            if (
                "synthetic" in event.event_id.lower()
                or "soak" in event.event_id.lower()
            ):
                raise ValueError("baseline contains a synthetic/soak event identifier")
            event = replace(event, run_id=self.config.run_id)
            assessed = quality.assess(event, mode="replay", now=event.event_time)
            training_snapshots.extend(engine.process(assessed))
            counts[event.event_type.value] += 1
            maximum = (
                event.event_time if maximum is None else max(maximum, event.event_time)
            )
        training_snapshots.extend(engine.flush())
        if maximum is None:
            raise ValueError(f"baseline file is empty: {path}")
        # 参考：[R08：TSB-AD；R09：Towards Unbiased Evaluation】主要参考了时间切分与评测偏差的概念方法
        # 解决的问题：baseline 包含区间开始后的事件会产生未来信息泄漏
        # 解决方法：要求 baseline 的最后事件严格早于 evaluation interval 开始
        if maximum >= interval_start:
            raise ValueError(
                "baseline leakage: baseline event is not strictly before evaluation"
            )
        state = engine.export_baseline_state()  # 交给 evaluation 引擎的阈值状态
        return state, {
            "events": sum(counts.values()),
            "event_types": dict(sorted(counts.items())),
            "last_event_time": maximum.isoformat(),
            "baseline_sha256": canonical_sha256(state),
            "snapshots": len(training_snapshots),
        }, training_snapshots

    def _evaluate_interval(
        self,
        interval,
        path: Path,
        baseline_state: dict[str, Any],
        *,
        dataset_id: str,
    ) -> tuple[list[ReplayStep], list[DetectedEvent], dict[str, Any]]:
        quality = EventQualityGate()
        engine = LightweightFactorEngine(
            cadences=self.config.cadences,
            min_history_days=self.config.min_history_days,
            baseline_days=self.config.baseline_days,
        )
        # 问题：evaluation 窗口若继续更新 baseline，会在测试过程中改变阈值
        # 解决方法：测试引擎导入训练状态后立即冻结，后续窗口只能读取阈值。
        engine.import_baseline_state(baseline_state, freeze=True)
        detector = CEPDetector()  # 每个审阅区间使用独立 detector 状态
        snapshots: list[FactorSnapshot] = []  # 按事件时间产生的因子窗口
        # snapshot 对象 ID → (引用总数, 能在本次输入中解析的引用数)
        trace_resolution: dict[int, tuple[int, int]] = {}
        counts: Counter[str] = Counter()
        recent: OrderedDict[str, None] = OrderedDict()  # 核对 source_event_ids
        for event in iter_events(path):
            if event.source != "alpaca" or event.mode != "replay_real":
                raise ValueError(
                    f"evaluation contains non-real source: {event.source}/{event.mode}"
                )
            if event.dataset_id != dataset_id:
                raise ValueError(
                    "evaluation event dataset_id does not match the manifest"
                )
            if event.provenance.get("interval_id") != interval.interval_id:
                raise ValueError(
                    "evaluation event interval provenance does not match the manifest"
                )
            if event.provenance.get("phase") != "evaluation":
                raise ValueError(
                    "evaluation event is missing evaluation phase provenance"
                )
            if not interval.started_at <= event.event_time <= interval.ended_at:
                # evaluation 文件不能包含人工审阅区间之外的事件。
                raise ValueError("evaluation event falls outside its reviewed interval")
            if (
                "synthetic" in event.event_id.lower()
                or "soak" in event.event_id.lower()
            ):
                raise ValueError(
                    "evaluation contains a synthetic/soak event identifier"
                )
            event = replace(event, run_id=self.config.run_id)
            assessed = quality.assess(event, mode="replay", now=event.event_time)
            _remember_event(recent, assessed.event_id)
            emitted = engine.process(assessed)
            for snapshot in emitted:
                trace_resolution[id(snapshot)] = (
                    len(snapshot.source_event_ids),
                    sum(event_id in recent for event_id in snapshot.source_event_ids),
                )
            snapshots.extend(emitted)
            counts[event.event_type.value] += 1
        flushed = engine.flush()
        for snapshot in flushed:
            trace_resolution[id(snapshot)] = (
                len(snapshot.source_event_ids),
                sum(event_id in recent for event_id in snapshot.source_event_ids),
            )
        snapshots.extend(flushed)
        # 目标：验证测试期间 baseline 确实没有变化。
        # 关键设计：评测结束后重新计算阈值摘要，与导入前状态进行比较。
        if _threshold_state_hash(
            engine.export_baseline_state()
        ) != _threshold_state_hash(baseline_state):
            raise ValueError("frozen baseline changed during evaluation")
        snapshots = sorted(
            snapshots, key=lambda item: (item.event_time, item.ticker, item.cadence)
        )
        snapshots = [
            item
            for item in snapshots
            if (item.window_start or item.event_time) < interval.ended_at
            and item.event_time > interval.started_at
        ]
        if not snapshots:
            # 没有snapshot说明事件被覆盖或窗口边界不满足评测条件
            raise ValueError(f"interval {interval.interval_id}: no factor snapshots")
        # 问题：warm-up snapshot的阈值不稳定，不适合计算 precision/recall
        # 解决方法：只要区间内仍有 warm-up snapshot，就不生成评价指标
        warming = [
            item
            for item in snapshots
            if item.warmup_status != "ready"
            or any(
                state.get("state") == "warmup" for state in item.factor_states.values()
            )
        ]
        if warming:
            raise ValueError(
                f"interval {interval.interval_id}: {len(warming)} snapshots are still warming_up"
            )
        traces_resolved = 0
        traced_ids = 0
        steps: list[ReplayStep] = []
        detections: list[DetectedEvent] = []
        quality_good = 0
        # 目标：让每条告警都能从结果追踪到因子和原始输入
        # 关键设计：每个 ReplayStep 保存snapshot、CEP 结果、truth 上下文和原始事件引用
        for snapshot in snapshots:
            result = detector.process(snapshot, detected_at=snapshot.event_time)
            source_ids = snapshot.source_event_ids
            traced, resolved = trace_resolution.get(id(snapshot), (len(source_ids), 0))
            traced_ids += traced
            traces_resolved += resolved
            quality_good += snapshot.data_quality.get("status") == "good"
            detection_id = None
            if result.is_alert:
                primary = _primary_pattern(result)
                if primary is None:
                    # 正式告警必须能够指出一个已经完成的主模式。
                    raise ValueError("alert result has no completed primary pattern")
                detection_id = _detection_id(interval.interval_id, result)
                if result.ticker == interval.ticker:
                    detections.append(
                        DetectedEvent(
                            detection_id=detection_id,
                            ticker=result.ticker,
                            pattern=primary.name,
                            direction=primary.direction,
                            detected_at=result.event_time,
                        )
                    )
            steps.append(
                ReplayStep(
                    run_id=self.config.run_id,
                    interval_id=interval.interval_id,
                    snapshot=snapshot,
                    detection=result,
                    truth_kind=interval.kind,
                    truth_event_id=interval.event_id,
                    detection_id=detection_id
                    if result.ticker == interval.ticker
                    else None,
                    match_status="context_alert"
                    if result.is_alert and result.ticker != interval.ticker
                    else "none",
                )
            )
        return (
            steps,
            detections,
            {
                "events": sum(counts.values()),
                "event_types": dict(sorted(counts.items())),
                "snapshots": len(snapshots),
                "good_quality_snapshots": quality_good,
                "trace_ids": traced_ids,
                "resolved_trace_ids": traces_resolved,
            },
        )

    def run(self) -> dict[str, Any]:
        # 目标：让每个审阅区间成为相互独立、可重复的评测单元
        # 解决方法：逐区间校验哈希、建立并冻结 baseline，再统一汇总事件级指标和报告
        manifest, registry = self._validate_inputs()
        manifest_by_id = {item["interval_id"]: item for item in manifest["intervals"]}
        all_steps: list[ReplayStep] = []
        detections: list[DetectedEvent] = []
        isolation_forest_results: list[DetectedEvent] = []
        baseline_summaries = []
        interval_summaries = []
        for interval in registry.intervals:
            interval_manifest = manifest_by_id[interval.interval_id]
            baseline_path = resolve_artifact(
                self.config.dataset_manifest, interval_manifest["baseline"]["path"]
            )
            evaluation_path = resolve_artifact(
                self.config.dataset_manifest, interval_manifest["evaluation"]["path"]
            )
            for name, path, expected in (
                ("baseline", baseline_path, interval_manifest["baseline"]["sha256"]),
                (
                    "evaluation",
                    evaluation_path,
                    interval_manifest["evaluation"]["sha256"],
                ),
            ):
                actual = file_sha256(path)
                if actual != expected:
                    # 文件变化时立即失败，避免同一 run_id 对应不同输入数据。
                    raise ValueError(
                        f"interval {interval.interval_id}: {name} checksum mismatch"
                    )
            baseline_state, baseline_summary, training_snapshots = self._train_baseline(
                baseline_path,
                interval.started_at,
                dataset_id=manifest["dataset_id"],
                interval_id=interval.interval_id,
            )
            steps, interval_detections, interval_summary = self._evaluate_interval(
                interval,
                evaluation_path,
                baseline_state,
                dataset_id=manifest["dataset_id"],
            )
            _, interval_if_detections = isolation_forest_detections(
                training_snapshots,
                [step.snapshot for step in steps],
            )
            if baseline_summary["events"] != interval_manifest["baseline"]["events"]:
                raise ValueError(
                    f"interval {interval.interval_id}: baseline event count mismatch"
                )
            if interval_summary["events"] != interval_manifest["evaluation"]["events"]:
                raise ValueError(
                    f"interval {interval.interval_id}: evaluation event count mismatch"
                )
            baseline_summaries.append(
                {"interval_id": interval.interval_id, **baseline_summary}
            )
            interval_summaries.append(
                {"interval_id": interval.interval_id, **interval_summary}
            )
            all_steps.extend(steps)
            detections.extend(interval_detections)
            isolation_forest_results.extend(interval_if_detections)

        truth: list[GroundTruthEvent] = [
            item.to_ground_truth()
            for item in registry.intervals
            if item.kind == "anomaly"
        ]
        # 解决的问题：人工事件类别与 CEP pattern 名称不同，不应直接被算成漏检。
        # 解决方法：主指标匹配 ticker 和方向，pattern agreement 作为独立的次要指标报告。
        matches, false_positives, missed = match_events(
            truth, detections, require_pattern=False
        )
        metrics = compute_event_metrics(
            truth,
            detections,
            require_pattern=False,
            cooldown=timedelta(minutes=5),
        )
        isolation_forest_metrics = compute_event_metrics(
            truth,
            isolation_forest_results,
            require_pattern=False,
            cooldown=timedelta(minutes=5),
        )
        confidence = bootstrap_confidence_intervals(
            truth,
            detections,
            samples=self.config.bootstrap_samples,
            require_pattern=False,
        )
        reviewed_hours = sum(
            (item.ended_at - item.started_at).total_seconds() / 3600
            for item in registry.intervals
        )
        metrics.alerts_per_ticker_hour = (
            len(detections) / reviewed_hours if reviewed_hours else 0.0
        )
        isolation_forest_metrics.alerts_per_ticker_hour = (
            len(isolation_forest_results) / reviewed_hours if reviewed_hours else 0.0
        )
        matched_detection_ids = {item.detection.detection_id for item in matches}
        false_detection_ids = {item.detection_id for item in false_positives}
        missed_event_ids = {item.event_id for item in missed}
        for step in all_steps:
            if step.detection_id in matched_detection_ids:
                step.match_status = "tp"
            elif step.detection_id in false_detection_ids:
                step.match_status = "fp"
            elif step.truth_event_id in missed_event_ids:
                step.match_status = "fn_context"

        pattern_comparable = [
            match for match in matches if match.truth.pattern in PATTERN_SEVERITY
        ]
        pattern_agreement = (
            sum(
                match.truth.pattern == match.detection.pattern
                for match in pattern_comparable
            )
            / len(pattern_comparable)
            if pattern_comparable
            else 0.0
        )
        total_snapshots = sum(item["snapshots"] for item in interval_summaries)
        total_good = sum(item["good_quality_snapshots"] for item in interval_summaries)
        total_trace_ids = sum(item["trace_ids"] for item in interval_summaries)
        resolved_trace_ids = sum(
            item["resolved_trace_ids"] for item in interval_summaries
        )
        event_rows = [
            {
                "status": "TP",
                "event_id": item.truth.event_id,
                "interval_id": item.truth.interval_id,
                "ticker": item.truth.ticker,
                "expected_pattern": item.truth.pattern,
                "detected_pattern": item.detection.pattern,
                "direction": item.truth.direction,
                "started_at": item.truth.started_at.isoformat(),
                "detected_at": item.detection.detected_at.isoformat(),
                "delay_seconds": item.delay_seconds,
            }
            for item in matches
        ]
        event_rows.extend(
            {
                "status": "FN",
                "event_id": item.event_id,
                "interval_id": item.interval_id,
                "ticker": item.ticker,
                "expected_pattern": item.pattern,
                "detected_pattern": None,
                "direction": item.direction,
                "started_at": item.started_at.isoformat(),
                "detected_at": None,
                "delay_seconds": None,
            }
            for item in missed
        )
        event_rows.extend(
            {
                "status": "FP",
                "event_id": None,
                "interval_id": item.detection_id.split(":", 1)[0],
                "ticker": item.ticker,
                "expected_pattern": None,
                "detected_pattern": item.pattern,
                "direction": item.direction,
                "started_at": None,
                "detected_at": item.detected_at.isoformat(),
                "delay_seconds": None,
            }
            for item in false_positives
        )
        result = {
            "run_id": self.config.run_id,
            "data_kind": "real_historical",
            "coverage": manifest["coverage"],
            "dataset_id": manifest["dataset_id"],
            "labels_sha256": registry.digest,
            "baseline_sha256": canonical_sha256(baseline_summaries),
            "detector_version": self.config.detector_version,
            "metrics": metrics.to_dict(),
            "comparison": {
                "data_kind": "real_historical",
                "labels_frozen": registry.frozen,
                "feature_contract": list(FACTOR_GROUPS),
                "config": {
                    "contamination": 0.05,
                    "random_state": 42,
                    "protocol": "per-interval baseline fit; shared evaluation snapshots",
                },
                "methods": {
                    "factor_cep": metrics.to_dict(),
                    "isolation_forest": isolation_forest_metrics.to_dict(),
                },
            },
            "bootstrap_95_ci": {
                name: list(values) for name, values in confidence.items()
            },
            "auxiliary": {
                "pattern_agreement": pattern_agreement,
                "pattern_agreement_matches": len(pattern_comparable),
                "reviewed_ticker_hours": reviewed_hours,
                "false_alerts_per_reviewed_ticker_hour": (
                    len(false_positives) / reviewed_hours if reviewed_hours else 0.0
                ),
                "quality_good_rate": total_good / total_snapshots
                if total_snapshots
                else 0.0,
                "traceability_rate": (
                    resolved_trace_ids / total_trace_ids if total_trace_ids else 1.0
                ),
                "accuracy_reported": False,
            },
            "counts": {
                "reviewed_intervals": len(registry.intervals),
                "anomaly_intervals": len(truth),
                "normal_intervals": sum(
                    item.kind == "normal" for item in registry.intervals
                ),
                "snapshots": total_snapshots,
                "detections": len(detections),
            },
            "events": sorted(
                event_rows,
                key=lambda item: (
                    item["status"],
                    item.get("detected_at") or item.get("started_at") or "",
                ),
            ),
            "intervals": [item.to_dict() for item in registry.intervals],
            "baseline_runs": baseline_summaries,
            "interval_runs": interval_summaries,
        }
        output_dir = self.config.output_dir / self.config.run_id
        output_dir.mkdir(parents=True, exist_ok=True)
        metrics_path = output_dir / "metrics.json"
        trace_path = output_dir / "trace.jsonl"
        comparison_path = output_dir / "detector_comparison.json"
        run_manifest_path = output_dir / "run_manifest.json"
        html_path = output_dir / "replay_report.html"
        metrics_path.write_text(json.dumps(result, indent=2) + "\n")
        comparison_path.write_text(json.dumps(result["comparison"], indent=2) + "\n")
        with trace_path.open("w") as destination:
            for step in all_steps:
                destination.write(
                    json.dumps(step.to_dict(), separators=(",", ":")) + "\n"
                )
        run_manifest = {
            "schema_version": "marketstream-real-replay-run-v1",
            "run_id": self.config.run_id,
            "config": self.config.to_dict(),
            "dataset_manifest_sha256": file_sha256(self.config.dataset_manifest),
            "labels_sha256": registry.digest,
            "baseline_sha256": result["baseline_sha256"],
            "artifacts": {
                "metrics": {
                    "path": str(metrics_path),
                    "sha256": file_sha256(metrics_path),
                },
                "trace": {"path": str(trace_path), "sha256": file_sha256(trace_path)},
                "comparison": {
                    "path": str(comparison_path),
                    "sha256": file_sha256(comparison_path),
                },
                "html": {"path": str(html_path)},
            },
        }
        write_replay_html(html_path, result, [step.to_dict() for step in all_steps])
        run_manifest["artifacts"]["html"]["sha256"] = file_sha256(html_path)
        run_manifest_path.write_text(json.dumps(run_manifest, indent=2) + "\n")
        result["artifacts"] = {
            "run_manifest": str(run_manifest_path),
            "metrics": str(metrics_path),
            "trace": str(trace_path),
            "comparison": str(comparison_path),
            "html": str(html_path),
        }
        return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run strict deterministic real-market replay"
    )
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data/replay/runs"))
    parser.add_argument("--run-id")
    parser.add_argument("--cadences", type=int, nargs="+", default=[10, 60, 300])
    parser.add_argument("--min-history-days", type=int, default=5)
    parser.add_argument("--baseline-days", type=int, default=20)
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    kwargs = {
        "dataset_manifest": args.dataset_manifest,
        "labels_path": args.labels,
        "output_dir": args.output_dir,
        "cadences": tuple(args.cadences),
        "min_history_days": args.min_history_days,
        "baseline_days": args.baseline_days,
        "bootstrap_samples": args.bootstrap_samples,
    }
    if args.run_id:
        kwargs["run_id"] = args.run_id
    result = RealReplayEvaluator(ReplayRunConfig(**kwargs)).run()
    print(json.dumps({"run_id": result["run_id"], **result["artifacts"]}, indent=2))


if __name__ == "__main__":
    main()
