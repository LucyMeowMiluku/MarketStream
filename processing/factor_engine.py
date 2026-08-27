# =============================================================================
# function：把统一市场事件转换为 10s/1m/5m 的八因子快照和历史相对状态。
# 贡献：八因子组合、多维 baseline 键、暖机/冻结策略及有界流式状态
# 参考：MAD、市场残差和订单流失衡的概念、方法。[R04][R05][R06]
# 关键设计：按 ticker/cadence/session/slot 比较，且先评分、后写入当前窗口。
# 需要解决的问题：不同时段不可直接比较，当前异常可能稀释阈值，测试数据可能污染 baseline。
# 解决方法：分组维护有界历史，先用旧 baseline 评分再更新，并支持在正式评测中冻结 baseline。
# =============================================================================
"""Lightweight, bounded-memory factor computation over unified market events."""

from __future__ import annotations

import math
import hashlib
import json
import statistics
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from processing.event_models import FACTOR_GROUPS, FactorSnapshot, MarketEvent

NY = ZoneInfo("America/New_York")  # 市场时段按纽约时间判断
CADENCE_NAMES = {10: "10s", 60: "1m", 300: "5m"}  # 秒数到快照名称
SIGNED_FACTORS = {
    # 这些因子同时关心异常大小和上涨/下跌方向。
    "return_surprise",
    "quote_imbalance",
    "signed_trade_imbalance",
    "market_residual",
    "news_shock",
}


def market_session(value: datetime) -> str:
    local = value.astimezone(NY).time()
    if time(4, 0) <= local < time(9, 30):
        return "pre_market"
    if time(9, 30) <= local < time(16, 0):
        return "regular"
    if time(16, 0) <= local < time(20, 0):
        return "post_market"
    return "closed"


def _floor_time(value: datetime, seconds: int) -> datetime:
    epoch = int(value.timestamp())
    return datetime.fromtimestamp(epoch - epoch % seconds, tz=timezone.utc)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


@dataclass(slots=True)
class BaselineSeries:
    max_samples: int  # 每条 baseline 最多保留的历史样本数
    values: deque[tuple[date, float]] = field(init=False)  # 交易日和因子值

    def __post_init__(self) -> None:
        self.values = deque(maxlen=self.max_samples)

    def add(self, session_date: date, value: float) -> None:
        if math.isfinite(value):
            self.values.append((session_date, value))

    @property
    def samples(self) -> list[float]:
        return [value for _, value in self.values]

    @property
    def distinct_days(self) -> int:
        return len({session_date for session_date, _ in self.values})

    def summary(self) -> tuple[float, float, float, float]:
        # 参考：[R04：Rousseeuw & Croux, 1993] 中位数MAD比标准差更不容易被少量极端值影响
        # 关键设计：在使用MAD的同时保留经验高分位数，不忽略（ticker,time)出现的尾部情况
        values = self.samples
        if not values:
            return 0.0, 0.0, 0.0, 0.0
        median = statistics.median(values)  # 历史正常水平的中心
        mad = statistics.median(abs(value - median) for value in values)  # 稳健离散程度
        ordered = sorted(values)  # 用于计算经验尾部分位数

        def quantile(probability: float) -> float:
            index = min(
                len(ordered) - 1, max(0, math.ceil(probability * len(ordered)) - 1)
            )
            return ordered[index]

        return median, mad, quantile(0.995), quantile(0.999)


# 目标：首先在一个窗口内汇总成交、报价、K 线和新闻，为后续计算因子提供需要的input；然后再计算八个因子
# 关键设计：事件引用、质量标记、headline 和集合长度都有上限，支持长期运行和警报异常的回溯
@dataclass(slots=True)
class WindowAccumulator:
    start: datetime
    end: datetime
    # 价格
    first_price: float | None = None  # 窗口第一条有效价格
    last_price: float | None = None  # 窗口最后一条有效价格
    high: float | None = None
    low: float | None = None
    price_sum: float = 0.0
    price_count: int = 0
    # 成交
    trade_volume: float = 0.0
    bar_volume: float = 0.0
    buy_volume: float = 0.0  # 买方成交量
    sell_volume: float = 0.0  # 卖方成交量
    # 报价
    bid_price: float | None = None
    ask_price: float | None = None
    bid_size: float = 0.0
    ask_size: float = 0.0
    # 新闻
    news_scores: list[float] = field(default_factory=list)
    news_headlines: deque[str] = field(default_factory=lambda: deque(maxlen=5))
    # 用于检测duplicate和out_of_order
    event_ids: deque[str] = field(default_factory=lambda: deque(maxlen=128))
    event_count: int = 0
    event_type_counts: dict[str, int] = field(default_factory=dict)
    quality_flags: set[str] = field(default_factory=set)
    first_received_at: datetime | None = None
    last_received_at: datetime | None = None
    run_id: str | None = None
    dataset_id: str | None = None
    mode: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    def _record_price(self, price: float) -> None:
        if price <= 0:
            return
        if self.first_price is None:
            self.first_price = price
        self.last_price = price
        self.high = price if self.high is None else max(self.high, price)
        self.low = price if self.low is None else min(self.low, price)
        self.price_sum += price
        self.price_count += 1

    def update(self, event: MarketEvent) -> None:
        payload = event.payload
        self.event_ids.append(event.event_id)
        self.event_count += 1
        kind = event.event_type.value
        self.event_type_counts[kind] = self.event_type_counts.get(kind, 0) + 1
        self.quality_flags.update(event.quality_flags)
        self.run_id = event.run_id or self.run_id
        self.dataset_id = event.dataset_id or self.dataset_id
        self.mode = event.mode or self.mode
        if event.provenance:
            self.provenance.update(event.provenance)
        if self.first_received_at is None:
            self.first_received_at = event.received_at
        self.last_received_at = event.received_at

        # 遇到的问题：重复或乱序事件如果参与累计，会同时污染价格、成交量和新闻因子
        # 解决方法：保留其质量tag用于test，但不把其数值加入窗口统计
        # 如果重复、乱序，直接return，不会改计算好数，防止成交加两次或者乱序影响last price、high low
        if {"duplicate", "out_of_order"}.intersection(event.quality_flags):
            return
        # 四种事件类型对应的参数更新
        if event.event_type.value == "trade":
            price = _safe_float(payload.get("price"))
            size = max(0.0, _safe_float(payload.get("size")))
            self._record_price(price)
            self.trade_volume += size
            midpoint = None
            if self.bid_price and self.ask_price:
                # 上游没有 side 时，用最新 bid/ask 中点近似判断成交方向。
                midpoint = (self.bid_price + self.ask_price) / 2
            side = str(payload.get("side", "")).lower()
            if side in {"buy", "b"} or (
                not side and midpoint is not None and price >= midpoint
            ):
                self.buy_volume += size
            elif side in {"sell", "s"} or (
                not side and midpoint is not None and price < midpoint
            ):
                self.sell_volume += size
        elif event.event_type.value == "bar":
            # bar 的 OHLC 都参与窗口 high/low 和平均价格统计。
            for name in ("open", "high", "low", "close"):
                self._record_price(_safe_float(payload.get(name)))
            self.bar_volume += max(0.0, _safe_float(payload.get("volume")))
        elif event.event_type.value == "quote":
            self.bid_price = _safe_float(payload.get("bid_price")) or self.bid_price
            self.ask_price = _safe_float(payload.get("ask_price")) or self.ask_price
            self.bid_size = max(0.0, _safe_float(payload.get("bid_size")))
            self.ask_size = max(0.0, _safe_float(payload.get("ask_size")))
        elif event.event_type.value == "news":
            # headline 只保留少量样本用于告警解释，因子计算使用情绪分数。
            self.news_scores.append(_safe_float(payload.get("sentiment_score")))
            headline = str(payload.get("headline", "")).strip()
            if headline:
                self.news_headlines.append(headline)


class LightweightFactorEngine:
    """Convert events into 10-second, 1-minute, and 5-minute snapshots.
    All collections are capped. Baselines are keyed by ticker, session, cadence,
    and intraday slot so regular, pre-market, and post-market behavior do not mix.
    """

    def __init__(
        self,
        *,
        cadences: tuple[int, ...] = (10, 60, 300),
        min_history_days: int = 5,
        baseline_days: int = 20,
        max_tickers: int = 64,
        frozen_baselines: bool = False,
    ) -> None:
        self.cadences = tuple(sorted(cadences))
        self.min_history_days = min_history_days
        self.baseline_days = baseline_days
        self.max_tickers = max_tickers
        self._frozen_baselines = frozen_baselines
        self._baseline_version = "rolling-mad-v1"  # 快照中记录使用的阈值版本
        self._windows: OrderedDict[tuple[str, int], WindowAccumulator] = OrderedDict()
        self._baselines: dict[tuple[str, int, str, int, str], BaselineSeries] = {}
        self._previous_close: dict[tuple[str, int], float] = {}
        self._benchmark_returns: dict[tuple[int, str], tuple[datetime, float]] = {}
        self._trading_days: dict[str, deque[date]] = {}
        self._known_tickers: OrderedDict[str, None] = OrderedDict()

    # 处理每个event，返回八个因子的计算结果snapshot
    def process(self, event: MarketEvent) -> list[FactorSnapshot]:
        # 目标：同一事件同时生成 10s、1m 和 5m 三种时间窗口下的snapshot
        # 关键设计：时间窗口就需要处理数量上限和边界问题，当跨过边界时先结束旧窗口，再把当前事件加入新窗口，避免事件重复归属
        self._touch_ticker(event.ticker)
        snapshots: list[FactorSnapshot] = []
        for cadence in self.cadences:
            key = (event.ticker, cadence)
            current = self._windows.get(key)
            start = _floor_time(event.event_time, cadence)
            if current is None:
                # 第一次看到该 ticker/cadence时创建窗口
                current = WindowAccumulator(
                    start=start, end=start + timedelta(seconds=cadence)
                )
                self._windows[key] = current
            elif event.event_time >= current.end:
                # 当前事件已进入新窗口：先输出旧窗口，再创建新窗口
                snapshots.append(self._finalize(event.ticker, cadence, current))
                current = WindowAccumulator(
                    start=start, end=start + timedelta(seconds=cadence)
                )
                self._windows[key] = current
            elif event.event_time < current.start:
                # 已封口窗口之前的迟到事件不能回写进历史窗口
                current.quality_flags.add("out_of_order")
                continue
            current.update(event)
            self._windows.move_to_end(key)
        return snapshots

    def flush(self, until: datetime | None = None) -> list[FactorSnapshot]:
        cutoff = until or datetime.max.replace(tzinfo=timezone.utc)
        snapshots: list[FactorSnapshot] = []
        for key, window in list(self._windows.items()):
            if window.end <= cutoff:
                snapshots.append(self._finalize(key[0], key[1], window))
                del self._windows[key]
        return sorted(
            snapshots, key=lambda item: (item.event_time, item.ticker, item.cadence)
        )

    @property
    def state_size(self) -> dict[str, int]:
        return {
            "tickers": len(self._known_tickers),
            "windows": len(self._windows),
            "baselines": len(self._baselines),
        }

    @property
    def frozen_baselines(self) -> bool:
        return self._frozen_baselines

    def export_baseline_state(self) -> dict[str, Any]:
        """Return a JSON-compatible threshold state for a frozen test replay."""
        return {
            "format": "marketstream-baseline-v1",
            "min_history_days": self.min_history_days,
            "baseline_days": self.baseline_days,
            "baselines": [
                {
                    "ticker": key[0],
                    "cadence": key[1],
                    "session": key[2],
                    "slot": key[3],
                    "name": key[4],
                    "values": [
                        [session_date.isoformat(), value]
                        for session_date, value in series.values
                    ],
                }
                for key, series in sorted(self._baselines.items())
            ],
            "trading_days": {
                ticker: [session_date.isoformat() for session_date in days]
                for ticker, days in sorted(self._trading_days.items())
            },
            "previous_close": [
                {"ticker": key[0], "cadence": key[1], "value": value}
                for key, value in sorted(self._previous_close.items())
            ],
            "benchmark_returns": [
                {
                    "cadence": key[0],
                    "ticker": key[1],
                    "event_time": value[0].isoformat(),
                    "return": value[1],
                }
                for key, value in sorted(self._benchmark_returns.items())
            ],
        }

    def import_baseline_state(
        self, state: dict[str, Any], *, freeze: bool = True
    ) -> None:
        # 参考内容：[R08：TSB-AD；R09：Towards Unbiased Evaluation] 测试数据不能参与阈值选择
        # 解决的问题：evaluation 数据若更新 baseline，会改变测试期间的“正常”定义
        # 解决方法：导入训练期状态后默认冻结，evaluation 只读取阈值、不写回历史
        if state.get("format") != "marketstream-baseline-v1":
            raise ValueError("unsupported baseline state format")
        self._baselines.clear()
        for record in state.get("baselines", []):
            key = (
                str(record["ticker"]),
                int(record["cadence"]),
                str(record["session"]),
                int(record["slot"]),
                str(record["name"]),
            )
            series = BaselineSeries(self.baseline_days)
            for session_date, value in record.get("values", []):
                series.add(date.fromisoformat(session_date), float(value))
            self._baselines[key] = series
        self._trading_days = {
            ticker: deque(
                (date.fromisoformat(item) for item in values),
                maxlen=self.baseline_days + 1,
            )
            for ticker, values in state.get("trading_days", {}).items()
        }
        self._previous_close = {
            (record["ticker"], int(record["cadence"])): float(record["value"])
            for record in state.get("previous_close", [])
        }
        self._benchmark_returns = {
            (int(record["cadence"]), record["ticker"]): (
                datetime.fromisoformat(record["event_time"]),
                float(record["return"]),
            )
            for record in state.get("benchmark_returns", [])
        }
        self._known_tickers = OrderedDict(
            (ticker, None) for ticker in self._trading_days
        )
        self._frozen_baselines = freeze
        canonical = json.dumps(state, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode()).hexdigest()[:12]
        self._baseline_version = (
            f"frozen-mad-v1:{digest}" if freeze else "loaded-mad-v1"
        )

    def _touch_ticker(self, ticker: str) -> None:
        # 目标：限制服务同时保存的 ticker 数量，防止状态无限增长。
        # 关键设计：按最久未使用顺序淘汰，并同步清理窗口、baseline、前收盘和交易日状态。
        if ticker in self._known_tickers:
            self._known_tickers.move_to_end(ticker)
            return
        self._known_tickers[ticker] = None
        if len(self._known_tickers) <= self.max_tickers:
            return
        # 超过上限时淘汰最久未使用的 ticker 及其全部关联状态。
        evicted, _ = self._known_tickers.popitem(last=False)
        self._windows = OrderedDict(
            (key, value) for key, value in self._windows.items() if key[0] != evicted
        )
        self._baselines = {
            key: value for key, value in self._baselines.items() if key[0] != evicted
        }
        self._previous_close = {
            key: value
            for key, value in self._previous_close.items()
            if key[0] != evicted
        }
        self._trading_days.pop(evicted, None)

    def _baseline_key(
        self,
        ticker: str,
        cadence: int,
        session: str,
        slot: int,
        name: str,
    ) -> tuple[str, int, str, int, str]:
        # 解决的问题：同一股票在盘前、常规盘、盘后和不同日内位置的正常水平不同。
        # 解决方法：使用 ticker、cadence、session、slot 和 factor 五维键分别维护 baseline。
        return ticker, cadence, session, slot, name

    def _series(self, key: tuple[str, int, str, int, str]) -> BaselineSeries:
        if key not in self._baselines:
            if self._frozen_baselines:
                return BaselineSeries(self.baseline_days)
            self._baselines[key] = BaselineSeries(self.baseline_days)
        return self._baselines[key]

    def _finalize(
        self, ticker: str, cadence: int, window: WindowAccumulator
    ) -> FactorSnapshot:
        session = market_session(window.end - timedelta(microseconds=1))
        local_end = window.end.astimezone(NY)
        slot = (
            local_end.hour * 3600 + local_end.minute * 60 + local_end.second
        ) // cadence
        session_date = local_end.date()
        days = self._trading_days.setdefault(
            ticker, deque(maxlen=self.baseline_days + 1)
        )
        if (
            not self._frozen_baselines
            and session_date not in days
            and session != "closed"
        ):
            days.append(session_date)

        close = window.last_price or self._previous_close.get((ticker, cadence), 0.0)
        previous = self._previous_close.get((ticker, cadence), close)  # 上一窗口收盘
        raw_return = (close - previous) / previous if close and previous else 0.0
        if close:
            self._previous_close[(ticker, cadence)] = close

        # 优先使用逐笔成交量；没有 trade 时才使用 bar volume，避免重复相加。
        volume = window.trade_volume if window.trade_volume > 0 else window.bar_volume
        price_range = 0.0
        if window.high and window.low and window.first_price:
            price_range = (window.high - window.low) / window.first_price  # 归一化振幅
        spread_bps = 0.0
        if window.bid_price and window.ask_price:
            mid = (window.bid_price + window.ask_price) / 2
            # 价差转成 basis points，便于比较不同价格水平的股票。
            spread_bps = (
                (window.ask_price - window.bid_price) / mid * 10_000 if mid else 0.0
            )

        volume_series = self._series(
            self._baseline_key(ticker, cadence, session, slot, "_volume")
        )
        range_series = self._series(
            self._baseline_key(ticker, cadence, session, slot, "_range")
        )
        spread_series = self._series(
            self._baseline_key(ticker, cadence, session, slot, "_spread")
        )
        return_series = self._series(
            self._baseline_key(ticker, cadence, session, slot, "_return")
        )
        volume_median = volume_series.summary()[0]
        range_median = range_series.summary()[0]
        spread_median = spread_series.summary()[0]
        return_median, return_mad, _, _ = return_series.summary()
        # 参考内容：[R04：Rousseeuw & Croux, 1993] 1.4826 用于把 MAD 调整为高斯一致尺度。
        # 解决的问题：历史过于平静时尺度可能为 0；使用 1e-6 下限避免除零和无穷分数。
        return_scale = max(1.4826 * return_mad, 1e-6)

        benchmark_return = self._latest_benchmark_return(ticker, cadence, window.end)
        if ticker in {"SPY", "QQQ"}:
            self._benchmark_returns[(cadence, ticker)] = (window.end, raw_return)
        quote_denominator = window.bid_size + window.ask_size  # 报价失衡分母
        trade_denominator = window.buy_volume + window.sell_volume  # 成交失衡分母
        news_mean = statistics.fmean(window.news_scores) if window.news_scores else 0.0

        # 目标：用八个容易解释的因子覆盖价格、活跃度、流动性、市场背景和新闻。
        # 参考内容：[R05：Cont, Kukanov & Stoikov] 订单流失衡与短期价格影响；
        # [R06：RBA Event-study Methodology] 用市场背景解释资产自身的异常收益。
        # 关键设计：公开概念提供因子含义；八因子的组合、三种 cadence 和输出结构由本项目设计。
        factor_values = {
            # 当前收益距离历史收益中位数多少个稳健尺度。
            "return_surprise": (raw_return - return_median) / return_scale,
            # 当前振幅、成交量和价差分别是同类历史中位数的多少倍。
            "volatility_burst": price_range / range_median if range_median > 0 else 0.0,
            "relative_volume": volume / volume_median if volume_median > 0 else 0.0,
            "spread_stress": spread_bps / spread_median if spread_median > 0 else 0.0,
            "quote_imbalance": (
                # 正数表示 bid size 更大，负数表示 ask size 更大。
                (window.bid_size - window.ask_size) / quote_denominator
                if quote_denominator
                else 0.0
            ),
            "signed_trade_imbalance": (
                # 正数表示买方成交占优，负数表示卖方成交占优。
                (window.buy_volume - window.sell_volume) / trade_denominator
                if trade_denominator
                else 0.0
            ),
            "market_residual": raw_return - benchmark_return,  # 扣除 SPY/QQQ 同期变化
            # 关键设计：新闻均值乘 log1p(条数)，既保留情绪方向和集中爆发，又避免条数线性放大。
            "news_shock": news_mean * math.log1p(len(window.news_scores)),
        }
        factor_values = {
            name: round(_safe_float(value), 8) for name, value in factor_values.items()
        }

        # 解决的问题：历史天数不足时阈值不稳定，容易产生没有依据的告警。
        # 解决方法：只输出 warmup 状态，直到同类历史覆盖足够交易日。
        ready = len(set(days)) >= self.min_history_days
        factor_states: dict[str, dict[str, Any]] = {}
        for name, value in factor_values.items():
            key = self._baseline_key(ticker, cadence, session, slot, name)
            series = self._series(key)
            median, mad, quantile_995, quantile_999 = series.summary()
            scale = max(1.4826 * mad, 1e-6)
            robust_z = (
                (value - median) / scale if series.samples else 0.0
            )  # 历史相对偏离
            if name in SIGNED_FACTORS:
                # 有方向因子用绝对距离判异常，再保留 up/down 方向。
                threshold = max(abs(quantile_995 - median), 4 * scale)
                extreme_threshold = max(abs(quantile_999 - median), 6 * scale)
                distance = abs(value - median)
                direction = "up" if value >= median else "down"
            else:
                # 单向因子只关注向上扩大，例如成交量和价差倍数。
                threshold = max(quantile_995, median + 4 * scale)
                extreme_threshold = max(quantile_999, median + 6 * scale)
                distance = value
                direction = "up"
            state = "warmup"
            if ready and series.distinct_days >= self.min_history_days:
                # elevated 使用较低阈值，extreme 使用更严格的尾部阈值。
                state = (
                    "extreme"
                    if distance >= extreme_threshold
                    else "elevated"
                    if distance >= threshold
                    else "normal"
                )
            factor_states[name] = {
                "group": FACTOR_GROUPS[name],
                "state": state,
                "direction": direction,
                "baseline": round(median, 8),
                "robust_z": round(robust_z, 4),
                "threshold": round(threshold, 8),
                "extreme_threshold": round(extreme_threshold, 8),
                "history_days": series.distinct_days,
            }
            # 解决的问题：若先写入当前值，异常会参与自己的 baseline，降低 robust_z。
            # 解决方法：先完成当前窗口评分，再把当前值写入历史；冻结时完全不写入。
            if not self._frozen_baselines:
                series.add(session_date, value)

        if not self._frozen_baselines:
            volume_series.add(session_date, volume)
            range_series.add(session_date, price_range)
            if spread_bps:
                spread_series.add(session_date, spread_bps)
            return_series.add(session_date, raw_return)

        # 目标：同时保留因子结果和输入质量证据。
        # 关键设计：因子层不静默丢弃整段观测，由 CEP 根据质量决定解释或抑制告警。
        severe_flags = {
            "duplicate",
            "out_of_order",
            "stale",
            "invalid_price",
            "crossed_quote",
        }
        quality_flags = sorted(window.quality_flags)
        data_quality = {
            "status": "degraded"
            if severe_flags.intersection(quality_flags)
            else "good",
            "flags": quality_flags,
            "session": session,
            "feed_event_count": window.event_count,
            "first_received_at": window.first_received_at.isoformat()
            if window.first_received_at
            else None,
            "last_received_at": window.last_received_at.isoformat()
            if window.last_received_at
            else None,
        }
        return FactorSnapshot(
            ticker=ticker,
            event_time=window.end,
            window_start=window.start,
            cadence=CADENCE_NAMES.get(cadence, f"{cadence}s"),
            factor_values=factor_values,
            factor_states=factor_states,
            baseline_version=f"{self._baseline_version}:{session}:{len(set(days))}d",
            data_quality=data_quality,
            warmup_status="ready" if ready else "warming_up",
            source_event_ids=list(window.event_ids),
            input_summary={
                "event_type_counts": dict(sorted(window.event_type_counts.items())),
                "first_price": window.first_price,
                "last_price": window.last_price,
                "bid_price": window.bid_price,
                "ask_price": window.ask_price,
                "bid_size": window.bid_size,
                "ask_size": window.ask_size,
                "trade_volume": window.trade_volume,
                "bar_volume": window.bar_volume,
                "news_count": len(window.news_scores),
                "news_headlines": list(window.news_headlines),
                "traced_source_event_ids": len(window.event_ids),
            },
            run_id=window.run_id,
            dataset_id=window.dataset_id,
            mode=window.mode,
            provenance=window.provenance,
            legacy_features={
                "ticker": ticker,
                "window_start": int(window.start.timestamp() * 1000),
                "window_end": int(window.end.timestamp() * 1000),
                "avg_close": round(window.price_sum / window.price_count, 4)
                if window.price_count
                else round(close, 4),
                "first_close": round(window.first_price or close, 4),
                "last_close": round(close, 4),
                "price_change_rate": round(raw_return, 8),
                "total_volume": int(volume),
                "tick_count": window.price_count,
            },
        )

    def _latest_benchmark_return(
        self, ticker: str, cadence: int, event_time: datetime
    ) -> float:
        # 解决的问题：过期或不同 cadence 的市场收益会产生错误的个股残差。
        # 解决方法：只使用相同 cadence 且在两个窗口以内的 SPY/QQQ 收益。
        candidates = (
            ("QQQ", "SPY")
            if ticker not in {"QQQ", "SPY"}
            else tuple(item for item in ("SPY", "QQQ") if item != ticker)
        )
        for benchmark in candidates:
            latest = self._benchmark_returns.get((cadence, benchmark))
            if latest and event_time - latest[0] <= timedelta(seconds=cadence * 2):
                return latest[1]
        return 0.0
