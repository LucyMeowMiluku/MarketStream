# 来源归属（2026-10-22）：XI LU 主导方案选择与具体约束，AI 按确认方案生成／重构实现。
# 本注释不声明全部代码由本人手写；逐项原日志与未确认范围见
# docs/CORE_CODE_AUTHORSHIP_AND_REFERENCES_CN.md 及 report/ownership_evidence/08_Contribution_Attribution_Matrix_CN.md。
"""Bounded window state and time helpers for the factor engine."""

from __future__ import annotations

import math
import statistics
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

from processing.event_models import MarketEvent

NY = ZoneInfo("America/New_York")
CADENCE_NAMES = {10: "10s", 60: "1m", 300: "5m"}
SIGNED_FACTORS = {
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


def floor_time(value: datetime, seconds: int) -> datetime:
    epoch = int(value.timestamp())
    return datetime.fromtimestamp(epoch - epoch % seconds, tz=timezone.utc)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


@dataclass(slots=True)
class BaselineSeries:
    """Bounded factor history for one ticker/cadence/session/slot key."""

    max_samples: int
    values: deque[tuple[date, float]] = field(init=False)

    def __post_init__(self) -> None:
        # Do not use deque(maxlen=...). A retry for the same trading date must
        # replace that date, and an out-of-order old date must not evict a newer
        # observation.
        self.values = deque()

    def add(self, session_date: date, value: float) -> None:
        if math.isfinite(value):
            by_date = {day: sample for day, sample in self.values}
            by_date[session_date] = value
            self.values = deque(sorted(by_date.items())[-self.max_samples :])

    def samples_before(self, session_date: date | None = None) -> list[float]:
        return [
            value
            for day, value in self.values
            if session_date is None or day < session_date
        ]

    @property
    def samples(self) -> list[float]:
        return self.samples_before()

    @property
    def distinct_days(self) -> int:
        return len({session_date for session_date, _ in self.values})

    def distinct_days_before(self, session_date: date | None = None) -> int:
        return len(
            {
                day
                for day, _ in self.values
                if session_date is None or day < session_date
            }
        )

    def summary(self, before: date | None = None) -> tuple[float, float, float, float]:
        values = self.samples_before(before)
        if not values:
            return 0.0, 0.0, 0.0, 0.0
        median = statistics.median(values)
        mad = statistics.median(abs(value - median) for value in values)
        ordered = sorted(values)

        def quantile(probability: float) -> float:
            index = min(
                len(ordered) - 1,
                max(0, math.ceil(probability * len(ordered)) - 1),
            )
            return ordered[index]

        return median, mad, quantile(0.995), quantile(0.999)


@dataclass(slots=True)
class WindowAccumulator:
    """The bounded raw observations required to compute one factor snapshot."""

    start: datetime
    end: datetime
    first_price: float | None = None
    last_price: float | None = None
    high: float | None = None
    low: float | None = None
    price_sum: float = 0.0
    price_count: int = 0
    trade_volume: float = 0.0
    bar_volume: float = 0.0
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    bid_price: float | None = None
    ask_price: float | None = None
    bid_size: float = 0.0
    ask_size: float = 0.0
    news_scores: list[float] = field(default_factory=list)
    news_headlines: deque[str] = field(default_factory=lambda: deque(maxlen=5))
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
        self.first_received_at = self.first_received_at or event.received_at
        self.last_received_at = event.received_at
        if {"duplicate", "out_of_order"}.intersection(event.quality_flags):
            return
        if kind == "trade":
            self._update_trade(payload)
        elif kind == "bar":
            self._update_bar(payload)
        elif kind == "quote":
            self._update_quote(payload)
        elif kind == "news":
            self._update_news(payload)

    def _update_trade(self, payload: dict[str, Any]) -> None:
        price = safe_float(payload.get("price"))
        size = max(0.0, safe_float(payload.get("size")))
        self._record_price(price)
        self.trade_volume += size
        midpoint = (
            (self.bid_price + self.ask_price) / 2
            if self.bid_price and self.ask_price
            else None
        )
        side = str(payload.get("side", "")).lower()
        if side in {"buy", "b"} or (not side and midpoint is not None and price >= midpoint):
            self.buy_volume += size
        elif side in {"sell", "s"} or (not side and midpoint is not None and price < midpoint):
            self.sell_volume += size

    def _update_bar(self, payload: dict[str, Any]) -> None:
        for name in ("open", "high", "low", "close"):
            self._record_price(safe_float(payload.get(name)))
        self.bar_volume += max(0.0, safe_float(payload.get("volume")))

    def _update_quote(self, payload: dict[str, Any]) -> None:
        self.bid_price = safe_float(payload.get("bid_price")) or self.bid_price
        self.ask_price = safe_float(payload.get("ask_price")) or self.ask_price
        self.bid_size = max(0.0, safe_float(payload.get("bid_size")))
        self.ask_size = max(0.0, safe_float(payload.get("ask_size")))

    def _update_news(self, payload: dict[str, Any]) -> None:
        self.news_scores.append(safe_float(payload.get("sentiment_score")))
        headline = str(payload.get("headline", "")).strip()
        if headline:
            self.news_headlines.append(headline)
