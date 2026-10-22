# 来源归属（2026-10-22）：XI LU 主导方案选择与具体约束，AI 按确认方案生成／重构实现。
# 本注释不声明全部代码由本人手写；逐项原日志与未确认范围见
# docs/CORE_CODE_AUTHORSHIP_AND_REFERENCES_CN.md 及 report/ownership_evidence/08_Contribution_Attribution_Matrix_CN.md。
# =============================================================================
# function：提供防泄漏的时间切分、事件匹配、延迟、告警负担和置信区间指标。
# 贡献：面向 MarketStream 事件合同的一对一匹配规则、指标组合和数据结构。
# 参考边界：时序异常评测偏差与实时及时性原则来自公开研究。[R08][R09][R10]
# 关键设计：只允许向前一对一匹配；不使用对称窗口或 point adjustment 抬高命中。
# 需要解决的问题：一个告警可能重复命中多个事件，提前检测可能被算成 TP，逐点指标会高估效果。
# 解决方法：保持时间顺序，使用向前一对一事件匹配，并分别报告质量、延迟和告警负担。
# =============================================================================
"""Leakage-resistant event-level evaluation for streaming anomaly detectors."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Iterable

import numpy as np


@dataclass(frozen=True, slots=True)
class GroundTruthEvent:
    event_id: str  # 独立审阅的真实事件 ID
    ticker: str  # 事件对应的股票
    pattern: str  # 人工事件类别或预期模式
    direction: str  # up 或 down
    started_at: datetime  # 允许检测开始命中的时间
    ended_at: datetime  # 事件区间结束时间
    evidence_urls: tuple[str, ...] = ()
    label_status: str = "approved"
    confidence: float | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    data_kind: str = "synthetic"
    interval_id: str | None = None
    notes: str = ""


@dataclass(frozen=True, slots=True)
class DetectedEvent:
    detection_id: str  # 每条检测的唯一身份
    ticker: str
    pattern: str
    direction: str
    detected_at: datetime  # detector 首次完成模式的时间
    received_at: datetime | None = None  # 系统收到触发数据的时间
    persisted_at: datetime | None = None  # 告警成功落库时间


@dataclass(frozen=True, slots=True)
class EventMatch:
    truth: GroundTruthEvent
    detection: DetectedEvent
    delay_seconds: float


@dataclass(slots=True)
class EventMetrics:
    precision: float
    recall: float
    f1: float
    true_positives: int
    false_positives: int
    false_negatives: int
    delay_p50_seconds: float
    delay_p95_seconds: float
    delay_p99_seconds: float
    end_to_end_p50_seconds: float | None
    end_to_end_p95_seconds: float | None
    end_to_end_p99_seconds: float | None
    alerts_per_ticker_hour: float
    duplicate_alert_rate: float

    def to_dict(self) -> dict:
        return asdict(self)


def chronological_split(
    values: list,
    *,
    train_fraction: float = 0.6,
    validation_fraction: float = 0.2,
) -> tuple[list, list, list]:
    """Return a strict 60/20/20-style chronological split without shuffling."""
    # 参考内容：[R08：TSB-AD；R09：Towards Unbiased Evaluation] 时序评测必须避免未来信息泄漏。
    # 解决方法：保持原始时间顺序进行 train/validation/test 切分，不随机打乱。
    if train_fraction <= 0 or validation_fraction < 0 or train_fraction + validation_fraction >= 1:
        raise ValueError("fractions must leave a non-empty test partition")
    train_end = int(len(values) * train_fraction)  # train 结束下标
    validation_end = int(len(values) * (train_fraction + validation_fraction))
    return values[:train_end], values[train_end:validation_end], values[validation_end:]


def match_events(
    truth: Iterable[GroundTruthEvent],
    detections: Iterable[DetectedEvent],
    *,
    grace_after: timedelta = timedelta(0),
    require_pattern: bool = True,
) -> tuple[list[EventMatch], list[DetectedEvent], list[GroundTruthEvent]]:
    """One-to-one forward matching; a detection before event start never matches."""
    # 目标：让一个检测最多匹配一个真实事件。
    # 关键设计：truth 和 detection 先稳定排序，再用 unused 集合记录尚未使用的检测。
    truth_sorted = sorted(truth, key=lambda event: (event.started_at, event.event_id))
    detection_sorted = sorted(detections, key=lambda event: (event.detected_at, event.detection_id))
    unused = set(range(len(detection_sorted)))  # 尚未匹配的检测下标
    matches: list[EventMatch] = []
    missed: list[GroundTruthEvent] = []
    for expected in truth_sorted:
        eligible = []
        for index in unused:
            detection = detection_sorted[index]
            if detection.ticker != expected.ticker or detection.direction != expected.direction:
                # 股票或方向不同，不属于同一市场事件。
                continue
            if require_pattern and detection.pattern != expected.pattern:
                # 严格模式评测时，模式名称也必须一致。
                continue
            # 参考内容：[R08：TSB-AD；R10：Numenta Anomaly Benchmark] 评测应重视及时检测并避免宽松匹配。
            # 解决的问题：对称窗口可能把事件开始前的检测算成命中。
            # 解决方法：只允许向后的 grace，检测时间必须不早于事件开始。
            if expected.started_at <= detection.detected_at <= expected.ended_at + grace_after:
                eligible.append(index)
        if not eligible:
            missed.append(expected)
            continue
        # 多条检测都符合时，只选择最早一条作为首次检测。
        chosen = min(eligible, key=lambda index: detection_sorted[index].detected_at)
        unused.remove(chosen)
        detection = detection_sorted[chosen]
        matches.append(
            EventMatch(
                truth=expected,
                detection=detection,
                delay_seconds=(detection.detected_at - expected.started_at).total_seconds(),
            )
        )
    false_positives = [detection_sorted[index] for index in sorted(unused)]
    return matches, false_positives, missed


def _percentiles(values: list[float]) -> tuple[float, float, float]:
    if not values:
        return 0.0, 0.0, 0.0
    return tuple(float(value) for value in np.percentile(values, [50, 95, 99]))


def _duplicate_rate(detections: list[DetectedEvent], cooldown: timedelta) -> float:
    if not detections:
        return 0.0
    duplicates = 0  # cooldown 内重复出现的告警数量
    last: dict[tuple[str, str, str], datetime] = {}
    # 目标：衡量用户实际会收到多少同类重复告警。
    # 关键设计：使用与生产 cooldown 相同的 ticker/pattern/direction 组合判断重复。
    for detection in sorted(detections, key=lambda item: item.detected_at):
        key = (detection.ticker, detection.pattern, detection.direction)
        previous = last.get(key)
        if previous and detection.detected_at - previous < cooldown:
            duplicates += 1
        else:
            last[key] = detection.detected_at
    return duplicates / len(detections)


def compute_event_metrics(
    truth: Iterable[GroundTruthEvent],
    detections: Iterable[DetectedEvent],
    *,
    grace_after: timedelta = timedelta(0),
    cooldown: timedelta = timedelta(minutes=5),
    observation_start: datetime | None = None,
    observation_end: datetime | None = None,
    require_pattern: bool = True,
) -> EventMetrics:
    # 目标：同时评价检测质量、及时性和实际告警负担。
    # 关键设计：报告 precision/recall/F1、检测/端到端延迟、每 ticker-hour 告警数和重复率。
    truth_list = list(truth)
    detection_list = list(detections)
    matches, false_positives, missed = match_events(
        truth_list,
        detection_list,
        grace_after=grace_after,
        require_pattern=require_pattern,
    )
    true_positive_count = len(matches)
    precision = true_positive_count / len(detection_list) if detection_list else 0.0
    recall = true_positive_count / len(truth_list) if truth_list else 0.0
    # F1 使用 precision 和 recall 的调和平均，避免只优化其中一个指标。
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    delay_p50, delay_p95, delay_p99 = _percentiles([match.delay_seconds for match in matches])
    end_to_end = [
        (item.persisted_at - item.received_at).total_seconds()
        for item in detection_list
        if item.persisted_at is not None and item.received_at is not None
    ]
    e2e_p50, e2e_p95, e2e_p99 = _percentiles(end_to_end) if end_to_end else (None, None, None)
    timestamps = [event.started_at for event in truth_list] + [event.detected_at for event in detection_list]
    start = observation_start or (min(timestamps) if timestamps else None)
    end = observation_end or (max(timestamps) if timestamps else None)
    tickers = {event.ticker for event in truth_list} | {event.ticker for event in detection_list}
    ticker_hours = 0.0  # 观察时长 × 被观察 ticker 数量
    if start is not None and end is not None and tickers:
        ticker_hours = max((end - start).total_seconds() / 3600, 1 / 3600) * len(tickers)
    alert_rate = len(detection_list) / ticker_hours if ticker_hours else 0.0
    return EventMetrics(
        precision=precision,
        recall=recall,
        f1=f1,
        true_positives=true_positive_count,
        false_positives=len(false_positives),
        false_negatives=len(missed),
        delay_p50_seconds=delay_p50,
        delay_p95_seconds=delay_p95,
        delay_p99_seconds=delay_p99,
        end_to_end_p50_seconds=e2e_p50,
        end_to_end_p95_seconds=e2e_p95,
        end_to_end_p99_seconds=e2e_p99,
        alerts_per_ticker_hour=alert_rate,
        duplicate_alert_rate=_duplicate_rate(detection_list, cooldown),
    )


def bootstrap_confidence_intervals(
    truth: list[GroundTruthEvent],
    detections: list[DetectedEvent],
    *,
    samples: int = 1_000,
    seed: int = 42,
    require_pattern: bool = True,
) -> dict[str, tuple[float, float]]:
    """Event-level bootstrap 95% intervals for precision, recall, and F1."""
    # 目标：估计当前真实事件样本下 precision、recall 和 F1 的不确定性。
    # 关键设计：在事件层面有放回抽样并固定 seed，不把同一事件内的时间点当成独立样本。
    if not truth or samples <= 0:
        return {name: (0.0, 0.0) for name in ("precision", "recall", "f1")}
    matches, _, _ = match_events(truth, detections, require_pattern=require_pattern)
    matched_ids = {match.truth.event_id for match in matches}
    hits = np.array([event.event_id in matched_ids for event in truth], dtype=float)
    false_positive_count = max(0, len(detections) - len(matches))
    rng = np.random.default_rng(seed)  # 固定随机种子，保证区间可复现
    estimates = {name: [] for name in ("precision", "recall", "f1")}
    for _ in range(samples):
        sample_hits = rng.choice(hits, size=len(hits), replace=True)  # 事件级重采样
        true_positives = float(sample_hits.sum())
        recall = true_positives / len(sample_hits)
        precision = true_positives / (true_positives + false_positive_count) if true_positives else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        estimates["precision"].append(precision)
        estimates["recall"].append(recall)
        estimates["f1"].append(f1)
    return {
        name: tuple(float(value) for value in np.percentile(values, [2.5, 97.5]))
        for name, values in estimates.items()
    }
