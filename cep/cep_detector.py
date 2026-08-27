# ===========================================================================
# function：把 FactorSnapshot 关联为有方向、有时序且能够解释原因的异常事件
# 贡献：六类因子模式、严重度、质量抑制、冷却合并、解释和追溯结果的组合实现
# 参考：CEP 与自动机式事件关联是公开研究思想，未复制现有 CEP 引擎代码。[R07]
# 关键设计：多因素/多窗口确认优先；极端单因子仅作为受控例外
# 问题：单点阈值缺少上下文，同一事件重复告警，暖机数据误报且结果难以解释
# 解决方法：在有限窗口内组合因子事件，并加入质量抑制、cooldown、dedupe key 和证据输出
# ===========================================================================
"""
CEP 异常检测核心模块，主要进行异常判断 → 异常归属哪一类 → 异常事件解释。
该模块分为两个层次:
1.简单指标： 对于单个基础事件（如价格跳涨 2%、成交量激增 3 倍、情绪指标下降）会触发弱异常。
这个是必要的，避免漏报孤立的单点异常，这些事件并不是由多种因子导致的。这样也可以计算出孤立异常事件的recall。
2.复杂事件（核心创新点）： 基础事件的有序序列，由 cep.patterns 中的自动机进行识别，这会触发强异常
引入CEP之后对于复杂事件的异常报警是区别于之前的机器学习单点报警的最大区别。
它能够表达单点检测器无法表达的时序或者复合模式,并且具有更高的precision

该模块有两个调用入口，一个是供当前factor snapshot，另一个是供ml的features（用于兼容旧方法）。
1. 当前方法入口：process(FactorSnapshot)
   接收FactorSnapshot，将 elevated/extreme 因子转换为原子事件，并在对应的时间窗口中识别六类异常模式。
   该入口返回包含严重度、因子证据、原始事件引用、质量状态和解释文本的 DetectionResult。
   live data或者replay均使用该入口。
2. 旧ml兼容入口：score(features) 和 update(features)
   CEPDetector 是在之前的 BaseDetector上进更改的。
   因此可以接入旧的 EnsembleDetector 和ml/backtest.py，与机器学习baseline使用相同的评测流程进行比较。


Combines two layers:

1. **Point rules (simple indicators).** A lone primitive event (a 2% price
   jump, a 3x volume surge, a sentiment drop) raises a weak anomaly. This is the
   interpretable "simple threshold" baseline and gives the detector recall on
   isolated point anomalies.
2. **State automata (complex events).** Ordered sequences of primitives —
   recognised by the automata in :mod:`cep.patterns` — raise a strong anomaly.
   This is the novel CEP contribution: it expresses temporal/compound patterns a
   point detector cannot, with higher precision.

The detector implements :class:`ml.base_detector.BaseDetector`, so it drops into
the existing :class:`ml.ensemble.EnsembleDetector` and the ``ml/backtest.py``
evaluation harness unchanged — enabling an apples-to-apples comparison with the
ML baseline on the same data and metrics.

Per-window call contract (matches the ensemble / replay loop): ``score()`` is
called exactly once, then ``update()`` once. ``score()`` advances the automata
(emitting a detection on the window that completes a pattern) using the *current*
volume baseline; ``update()`` then folds this window into that baseline. So every
event is judged against history, never against itself.
"""

import hashlib
from collections import OrderedDict, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cep.events import EventDetector, EventThresholds
from cep.patterns import build_default_automata
from config.settings import settings
from ml.base_detector import BaseDetector
from processing.event_models import (
    AtomicEvent,
    DetectionResult,
    FactorSnapshot,
    PatternMatch,
)

# 定义六种异常模式
# 参考：[R07：SASE, Complex Event Processing over Streams] 参考有限窗口内关联事件的思想
# 关键设计：六类金融异常模式的名称、组合条件和严重度。这些由本项目根据检测目标设计，不是 SASE 预定义规则
PATTERN_PREFIX = "PATTERN:"

PATTERN_SEVERITY = {
    "stock_specific_dislocation": 0.82,  # 个股自身偏离
    "liquidity_pressure_move": 0.88,  # 流动性压力与价格共同变化
    "news_confirmed_move": 0.90,  # 新闻方向得到价格确认
    "flash_reversal": 0.86,  # 短时间快速反转
    "sustained_pressure": 0.92,  # 多窗口持续订单压力
    "cross_asset_shock": 0.95,  # 多资产共同冲击，严重度最高
}


@dataclass(slots=True)
class _Frame:
    snapshot: FactorSnapshot  # 当前时间窗口的完整因子状态
    atoms: list[AtomicEvent]  # 从 elevated/extreme 因子提取的事件


class CEPDetector(BaseDetector):
    """Complex-event-processing anomaly detector (point rules + automata).

    Supports **hierarchical composition**: base automata run first, and any
    that reach their accept state emit a synthetic ``PATTERN:<name>`` event.
    Meta-automata then run on the enriched event set, enabling higher-order
    patterns that consume sub-pattern completions as inputs.
    """

    def __init__(
        self,
        thresholds: EventThresholds | None = None,
        point_severity: float | None = None,
        max_gap: int | None = None,
        automata: list | None = None,
        meta_automata: list | None = None,
        cooldown_seconds: int | None = None,
        max_factor_frames: int = 64,
        enabled_factor_patterns: set[str] | None = None,
        max_tickers: int | None = None,
    ):
        self._events = EventDetector(
            thresholds
            or EventThresholds(
                price_jump=settings.cep_price_jump,
                volume_surge_ratio=settings.cep_volume_surge_ratio,
                sentiment_shift=settings.cep_sentiment_shift,
                sentiment_floor=settings.cep_sentiment_floor,
                volume_ewma_span=settings.cep_volume_ewma_span,
                min_volume_obs=settings.cep_min_volume_obs,
            )
        )
        gap = max_gap if max_gap is not None else settings.cep_max_gap
        if automata is not None:
            self._automata = automata
            self._meta_automata: list = meta_automata or []
        else:
            base, meta = build_default_automata(max_gap=gap)
            self._automata = base
            self._meta_automata = meta
        self._point_severity = (
            point_severity
            if point_severity is not None
            else settings.cep_point_severity
        )
        self._last_match: dict[str, str] = {}
        # 问题：CEP 持续接收事件时，历史状态可能无限增长
        # 解决方法：为每个 ticker/cadence 历史、跨资产历史和 ticker 集合设置硬上限
        self._factor_history: dict[tuple[str, str], deque[_Frame]] = defaultdict(
            lambda: deque(maxlen=max_factor_frames)
        )
        self._cross_asset_history: deque[_Frame] = deque(maxlen=256)
        self._cooldown = timedelta(
            seconds=(
                cooldown_seconds
                if cooldown_seconds is not None
                else getattr(settings, "cep_cooldown_seconds", 300)
            )
        )
        self._cooldown_until: dict[tuple[str, str, str], datetime] = {}
        self._enabled_factor_patterns = (
            set(PATTERN_SEVERITY)
            if enabled_factor_patterns is None
            else enabled_factor_patterns
        )
        self._max_tickers = max_tickers or getattr(settings, "factor_max_tickers", 64)
        self._factor_tickers: OrderedDict[str, None] = OrderedDict()

    @property
    def name(self) -> str:
        return "cep"

    # 主入口
    def process(
        self,
        snapshot: FactorSnapshot,
        *,
        detected_at: datetime | None = None,
    ) -> DetectionResult:
        """
        评估单个因子的snapshot ，并返回具有可解释性的结果
        """
        # 目标：把一个因子的snapshot转换成完整、可解释的检测结果
        # 关键设计：原子事件 → 模式关联 → 质量抑制 → cooldown 合并 → DetectionResult。
        detection_time = detected_at or datetime.now(timezone.utc)
        self._touch_factor_ticker(snapshot.ticker)
        atoms = self._atomic_events(snapshot)  # 当前窗口真正进入 CEP 的 proof
        key = (snapshot.ticker, snapshot.cadence)  # 不同时间尺度分别匹配
        history = self._factor_history[key]  # 该股票和 cadence 的近期窗口
        current = _Frame(snapshot=snapshot, atoms=atoms)
        completed, pending = self._match_patterns(current, history)
        completed.extend(self._match_cross_asset(current))
        completed = [
            item for item in completed if item.name in self._enabled_factor_patterns
        ]
        pending = [
            item for item in pending if item.name in self._enabled_factor_patterns
        ]
        # 问题：如果先写入历史，持续模式可能把当前窗口使用两次
        # 解决方法：先用“此前历史 + 当前帧”匹配，完成后再保存当前帧。
        history.append(current)
        self._cross_asset_history.append(current)

        # 目标：区分“检测到了模式”和“该模式可以作为正式告警”。
        # 解决方法：保留模式证据，但在 baseline 未准备好或数据质量严重下降时抑制告警。
        critical_quality = {"duplicate", "stale", "invalid_price", "crossed_quote"}
        quality_flags = set(snapshot.data_quality.get("flags", []))
        suppressed_reason = ""
        if snapshot.warmup_status != "ready":
            # baseline 不稳定时只保留模式，不发正式告警。
            suppressed_reason = "baseline warm-up is incomplete"
        elif quality_flags.intersection(critical_quality):
            # 严重质量标记说明模式可能由坏数据产生。
            suppressed_reason = "input data quality is degraded"

        # 多个模式同时完成时，选择预设严重度最高的模式作为主模式。
        primary = max(
            completed,
            key=lambda item: PATTERN_SEVERITY.get(item.name, 0.0),
            default=None,
        )
        is_alert = primary is not None and not suppressed_reason
        dedupe_key: str | None = None
        if primary is not None:
            # 解决的问题：同一个市场事件可能在连续窗口中反复命中，产生重复告警。
            # 解决方法：按 ticker+pattern+direction 设置 cooldown，并用稳定 dedupe_key 保证数据库幂等。
            cooldown_key = (snapshot.ticker, primary.name, primary.direction)
            cooldown_until = self._cooldown_until.get(cooldown_key)
            if is_alert and cooldown_until and snapshot.event_time < cooldown_until:
                # cooldown 内再次命中时改为 merged，不生成第二条正式告警。
                is_alert = False
                primary.status = "merged"
                suppressed_reason = "merged into an alert inside the cooldown window"
            if is_alert:
                self._cooldown_until[cooldown_key] = (
                    snapshot.event_time + self._cooldown
                )
            identity = (
                f"{snapshot.ticker}|{primary.name}|{primary.direction}|"
                f"{primary.started_at.isoformat()}"
            )
            dedupe_key = hashlib.sha256(identity.encode()).hexdigest()[:32]

        factor_evidence = {
            atom.factor: {
                "group": atom.group,
                "direction": atom.direction,
                "value": atom.value,
                "robust_z": atom.robust_z,
                "state": snapshot.factor_states.get(atom.factor, {}).get("state"),
            }
            for atom in atoms
        }
        base_score = PATTERN_SEVERITY.get(primary.name, 0.0) if primary else 0.0
        max_z = max(
            (abs(atom.robust_z) for atom in atoms), default=0.0
        )  # 最强单因子证据
        severity_score = min(1.0, max(base_score, max_z / 10)) if primary else 0.0
        severity = self._severity_label(severity_score)
        patterns = completed + pending
        explanation = self._explain(
            snapshot, primary, factor_evidence, suppressed_reason
        )
        if primary:
            self._last_match[snapshot.ticker] = primary.name
        else:
            self._last_match.pop(snapshot.ticker, None)
        return DetectionResult(
            ticker=snapshot.ticker,
            event_time=snapshot.event_time,
            detected_at=detection_time,
            cadence=snapshot.cadence,
            score=-round(severity_score, 6),
            severity=severity,
            is_alert=is_alert,
            direction=primary.direction if primary else None,
            atomic_events=atoms,
            patterns=patterns,
            factor_evidence=factor_evidence,
            source_event_ids=snapshot.source_event_ids,
            data_quality=snapshot.data_quality,
            explanation=explanation,
            dedupe_key=dedupe_key,
            run_id=snapshot.run_id,
            dataset_id=snapshot.dataset_id,
            mode=snapshot.mode,
            provenance=snapshot.provenance,
        )

    def _touch_factor_ticker(self, ticker: str) -> None:
        # 解决的问题：只删除 ticker 名称而保留历史或 cooldown，会造成状态残留和内存增长。
        # 解决方法：淘汰 ticker 时同步删除其历史、冷却和最后匹配状态。
        if ticker in self._factor_tickers:
            self._factor_tickers.move_to_end(ticker)
            return
        self._factor_tickers[ticker] = None
        if len(self._factor_tickers) <= self._max_tickers:
            return
        evicted, _ = self._factor_tickers.popitem(last=False)
        for key in [key for key in self._factor_history if key[0] == evicted]:
            del self._factor_history[key]
        for key in [key for key in self._cooldown_until if key[0] == evicted]:
            del self._cooldown_until[key]
        self._last_match.pop(evicted, None)

    @property
    def factor_state_size(self) -> dict[str, int]:
        return {
            "tickers": len(self._factor_tickers),
            "histories": len(self._factor_history),
            "cooldowns": len(self._cooldown_until),
            "cross_asset_frames": len(self._cross_asset_history),
        }

    @staticmethod
    # 提取异常因子
    # 目标：把 elevated/extreme 因子转换成 CEP 可以关联的原子事件
    # 关键设计：保留证据组、方向、robust_z 和源事件 event_id，支持跨组确认和结果解释
    def _atomic_events(snapshot: FactorSnapshot) -> list[AtomicEvent]:
        atoms: list[AtomicEvent] = []
        for factor, state in snapshot.factor_states.items():
            if state.get("state") not in {"elevated", "extreme"}:
                # normal/warmup 因子不应成为 CEP 原子事件。
                continue
            direction = state.get("direction", "up")
            name = f"{factor}:{direction}"
            atoms.append(
                AtomicEvent(
                    name=name,
                    group=state.get("group", "unknown"),
                    direction=direction,
                    event_time=snapshot.event_time,
                    factor=factor,
                    value=float(snapshot.factor_values.get(factor, 0.0)),
                    robust_z=float(state.get("robust_z", 0.0)),
                    source_event_ids=snapshot.source_event_ids,
                )
            )
        return atoms

    # 匹配异常模式
    # 参考内容：[R07：SASE, Complex Event Processing over Streams] 参考有限时间窗中的事件关联方法
    # 关键设计：六类金融模式、方向一致性、窗口长度和完成条件由本项目根据异常场景设计
    def _match_patterns(
        self,
        current: _Frame,
        history: deque[_Frame],
    ) -> tuple[list[PatternMatch], list[PatternMatch]]:

        snapshot = current.snapshot
        completed: list[PatternMatch] = []
        pending: list[PatternMatch] = []
        seconds = self._cadence_seconds(snapshot.cadence)
        recent = [
            frame
            for frame in history
            if snapshot.event_time - frame.snapshot.event_time
            <= timedelta(seconds=max(300, seconds * 5))
        ]
        current_by_factor = {atom.factor: atom for atom in current.atoms}
        recent_atoms = [
            atom for frame in recent for atom in frame.atoms
        ] + current.atoms

        # 目标1：识别个股自身偏离，而不是把整个市场上涨/下跌误认为个股异常。
        # 解决方法：要求价格异常与市场残差同向确认；只有 extreme return 才允许单因子例外。
        price = current_by_factor.get("return_surprise")
        residual = current_by_factor.get("market_residual")
        if price and residual and price.direction == residual.direction:
            # 同一窗口中价格和市场残差同向，说明变化不是市场基准单独造成的。
            completed.append(
                self._pattern(
                    "stock_specific_dislocation",
                    price.direction,
                    min(price.event_time, residual.event_time),
                    snapshot.event_time,
                    [price.factor, residual.factor],
                )
            )
        elif (
            price
            and snapshot.factor_states.get("return_surprise", {}).get("state")
            == "extreme"
        ):
            # 极端价格异常保留单因子入口，避免组合规则过严导致严重事件漏报。
            completed.append(
                self._pattern(
                    "stock_specific_dislocation",
                    price.direction,
                    price.event_time,
                    snapshot.event_time,
                    ["extreme:return_surprise"],
                )
            )

        # 目标2：识别由流动性和买卖压力共同支持的价格变化。
        # 解决方法：组合价差、同向 quote/trade pressure 与价格；证据不足时只记录 pending。
        liquidity = [
            atom
            for atom in recent_atoms
            if atom.factor
            in {"spread_stress", "quote_imbalance", "signed_trade_imbalance"}
            and snapshot.event_time - atom.event_time
            <= timedelta(seconds=max(60, seconds * 2))
        ]
        pressure = [atom for atom in liquidity if atom.factor != "spread_stress"]
        spread = next(
            (atom for atom in reversed(liquidity) if atom.factor == "spread_stress"),
            None,
        )
        aligned_pressure = next(
            (
                atom
                for atom in reversed(pressure)
                if price and atom.direction == price.direction
            ),
            None,
        )
        if price and spread and aligned_pressure:
            # 三类证据齐全且方向一致，才完成流动性压力模式。
            completed.append(
                self._pattern(
                    "liquidity_pressure_move",
                    price.direction,
                    min(
                        price.event_time, spread.event_time, aligned_pressure.event_time
                    ),
                    snapshot.event_time,
                    [spread.factor, aligned_pressure.factor, price.factor],
                )
            )
        elif spread or pressure:
            first = min(atom.event_time for atom in liquidity)
            pending.append(
                self._pattern(
                    "liquidity_pressure_move",
                    pressure[-1].direction if pressure else "up",
                    first,
                    None,
                    [atom.factor for atom in liquidity],
                    status="in_progress",
                )
            )

        # 目标3：识别新闻发生后得到价格方向确认的事件。
        # 解决方法：新闻必须在五分钟窗口内，并与后续价格异常方向一致。
        news = next(
            (
                atom
                for atom in reversed(recent_atoms)
                if atom.factor == "news_shock"
                and snapshot.event_time - atom.event_time <= timedelta(minutes=5)
            ),
            None,
        )
        if news and price and news.direction == price.direction:
            # 新闻方向与价格方向不一致时不能完成确认。
            completed.append(
                self._pattern(
                    "news_confirmed_move",
                    price.direction,
                    news.event_time,
                    snapshot.event_time,
                    [news.factor, price.factor],
                )
            )
        elif news:
            pending.append(
                self._pattern(
                    "news_confirmed_move",
                    news.direction,
                    news.event_time,
                    None,
                    [news.factor],
                    status="in_progress",
                )
            )

        # 目标4：识别短时间冲击后快速反向变化。
        # 解决方法：比较有限相邻窗口中的价格异常方向，方向翻转时完成模式。
        previous_price = next(
            (
                atom
                for atom in reversed(recent_atoms[: -len(current.atoms) or None])
                if atom.factor == "return_surprise"
                and snapshot.event_time - atom.event_time
                <= timedelta(seconds=seconds * 2)
            ),
            None,
        )
        if price and previous_price and price.direction != previous_price.direction:
            # 前后两个异常窗口方向相反，构成快速反转。
            completed.append(
                self._pattern(
                    "flash_reversal",
                    price.direction,
                    previous_price.event_time,
                    snapshot.event_time,
                    [previous_price.name, price.name],
                )
            )
        elif price:
            pending.append(
                self._pattern(
                    "flash_reversal",
                    price.direction,
                    price.event_time,
                    None,
                    [price.factor],
                    status="in_progress",
                )
            )

        # 目标5：识别持续订单压力，而不是一次偶然失衡。
        # 解决方法：要求至少三个不同窗口出现同向压力，并由同向价格异常确认。
        pressure_frames = (recent + [current])[-4:]
        for direction in ("up", "down"):
            directional = [
                atom
                for frame in pressure_frames
                for atom in frame.atoms
                if atom.factor in {"quote_imbalance", "signed_trade_imbalance"}
                and atom.direction == direction
            ]
            distinct_windows = len({atom.event_time for atom in directional})
            if distinct_windows >= 3 and price and price.direction == direction:
                # 压力必须来自至少三个不同时间窗口，不能用同一窗口多条因子凑数。
                completed.append(
                    self._pattern(
                        "sustained_pressure",
                        direction,
                        min(atom.event_time for atom in directional),
                        snapshot.event_time,
                        sorted({atom.factor for atom in directional} | {price.factor}),
                    )
                )
            elif distinct_windows >= 2:
                pending.append(
                    self._pattern(
                        "sustained_pressure",
                        direction,
                        min(atom.event_time for atom in directional),
                        None,
                        sorted({atom.factor for atom in directional}),
                        status="in_progress",
                    )
                )
        return self._unique_patterns(completed), self._unique_patterns(pending)

    def _match_cross_asset(self, current: _Frame) -> list[PatternMatch]:
        # 目标6：检查市场中是否多个股票同时发生异常
        # 解决方法：60 秒内至少三个标的同向异常，且必须包含 SPY 或 QQQ
        snapshot = current.snapshot
        recent = [
            frame
            for frame in self._cross_asset_history
            if timedelta(0)
            <= snapshot.event_time - frame.snapshot.event_time
            <= timedelta(seconds=60)
        ] + [current]
        result: list[PatternMatch] = []
        for direction in ("up", "down"):
            frames = [
                frame
                for frame in recent
                if any(
                    atom.factor == "return_surprise" and atom.direction == direction
                    for atom in frame.atoms
                )
            ]
            tickers = {frame.snapshot.ticker for frame in frames}
            if (
                len(tickers) >= 3
                and tickers.intersection({"SPY", "QQQ"})
                and snapshot.ticker in tickers
            ):
                # 至少三个标的且包含市场 ETF，才认为是跨资产而非少数个股共振。
                result.append(
                    self._pattern(
                        "cross_asset_shock",
                        direction,
                        min(frame.snapshot.event_time for frame in frames),
                        snapshot.event_time,
                        [f"return_surprise:{ticker}" for ticker in sorted(tickers)],
                    )
                )
        return result

    @staticmethod
    def _pattern(
        name: str,
        direction: str,
        started_at: datetime,
        completed_at: datetime | None,
        evidence: list[str],
        *,
        status: str = "completed",
    ) -> PatternMatch:
        return PatternMatch(
            name=name,
            direction=direction,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            evidence=evidence,
        )

    @staticmethod
    def _unique_patterns(patterns: list[PatternMatch]) -> list[PatternMatch]:
        unique: dict[tuple[str, str], PatternMatch] = {}
        for pattern in patterns:
            unique[(pattern.name, pattern.direction)] = pattern
        return list(unique.values())

    @staticmethod
    def _cadence_seconds(cadence: str) -> int:
        return {"10s": 10, "1m": 60, "5m": 300}.get(cadence, 60)

    @staticmethod
    def _severity_label(score: float) -> str:
        if score >= 0.95:
            return "critical"
        if score >= 0.85:
            return "high"
        if score > 0:
            return "medium"
        return "none"

    @staticmethod
    # 生成用户可读解释
    def _explain(
        snapshot: FactorSnapshot,
        primary: PatternMatch | None,
        evidence: dict[str, dict],
        suppressed_reason: str,
    ) -> str:
        if primary is None:
            if snapshot.warmup_status != "ready":
                return "No alert: baseline warm-up is incomplete."
            return "No confirmed multi-factor or persistent anomaly pattern."
        factors = ", ".join(primary.evidence)
        message = (
            f"{primary.name} ({primary.direction}) confirmed by {factors}. "
            f"Observed {len(evidence)} elevated or extreme factors."
        )
        if suppressed_reason:
            message += f" Alert suppressed because {suppressed_reason}."
        return message

    def score(self, features: dict) -> float:
        # 目标：保留旧ml features 实验的兼容入口
        # 关键设计：当前生产链必须调用 process(FactorSnapshot)；score() 不提供新八因子证据。
        ticker = features.get("ticker", "_default")
        events = self._events.detect(features)

        best_sev = 0.0
        best_name = ""

        # 参考：[R07：SASE] 参考自动机式事件关联思想；本代码未复制 SASE 实现。
        # 关键设计：旧入口先运行基础自动机，再把命中结果作为合成事件交给元自动机。
        fired: set[str] = set()
        for automaton in self._automata:
            sev = automaton.step(ticker, events, features=features)
            if sev > 0:
                fired.add(f"{PATTERN_PREFIX}{automaton.name}")
            if sev > best_sev:
                best_sev = sev
                best_name = automaton.name

        if self._meta_automata:
            enriched = events | fired
            for meta in self._meta_automata:
                sev = meta.step(ticker, enriched, features=features)
                if sev > 0 and sev >= best_sev:
                    best_sev = sev
                    best_name = meta.name

        if best_sev == 0.0 and events and self._point_severity > 0.0:
            best_sev = self._point_severity
            best_name = "point:" + "+".join(sorted(events))

        if best_sev > 0.0:
            self._last_match[ticker] = best_name
        else:
            self._last_match.pop(ticker, None)

        return -best_sev

    def update(self, features: dict) -> None:
        self._events.update(features)

    def last_match(self, ticker: str = "_default") -> str | None:
        """The pattern (or ``point:...``) that fired on this ticker's last window."""
        return self._last_match.get(ticker)
