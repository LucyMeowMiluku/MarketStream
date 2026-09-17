"""Pure calculations for the eight explainable factors."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from processing.factor_state import WindowAccumulator, safe_float


@dataclass(frozen=True, slots=True)
class WindowMetrics:
    close: float
    raw_return: float
    volume: float
    price_range: float
    spread_bps: float


def summarize_window(window: WindowAccumulator, previous_close: float) -> WindowMetrics:
    close = window.last_price or previous_close
    previous = previous_close or close
    raw_return = (close - previous) / previous if close and previous else 0.0
    volume = window.trade_volume if window.trade_volume > 0 else window.bar_volume
    price_range = 0.0
    if window.high and window.low and window.first_price:
        price_range = (window.high - window.low) / window.first_price
    spread_bps = 0.0
    if window.bid_price and window.ask_price:
        midpoint = (window.bid_price + window.ask_price) / 2
        spread_bps = (
            (window.ask_price - window.bid_price) / midpoint * 10_000
            if midpoint
            else 0.0
        )
    return WindowMetrics(close, raw_return, volume, price_range, spread_bps)


def calculate_factors(
    window: WindowAccumulator,
    metrics: WindowMetrics,
    *,
    return_median: float,
    return_mad: float,
    volume_median: float,
    range_median: float,
    spread_median: float,
    benchmark_return: float,
) -> dict[str, float]:
    return_scale = max(1.4826 * return_mad, 1e-6)
    quote_total = window.bid_size + window.ask_size
    trade_total = window.buy_volume + window.sell_volume
    news_mean = statistics.fmean(window.news_scores) if window.news_scores else 0.0
    values = {
        "return_surprise": (metrics.raw_return - return_median) / return_scale,
        "volatility_burst": metrics.price_range / range_median if range_median > 0 else 0.0,
        "relative_volume": metrics.volume / volume_median if volume_median > 0 else 0.0,
        "spread_stress": metrics.spread_bps / spread_median if spread_median > 0 else 0.0,
        "quote_imbalance": (
            (window.bid_size - window.ask_size) / quote_total if quote_total else 0.0
        ),
        "signed_trade_imbalance": (
            (window.buy_volume - window.sell_volume) / trade_total if trade_total else 0.0
        ),
        "market_residual": metrics.raw_return - benchmark_return,
        "news_shock": news_mean * math.log1p(len(window.news_scores)),
    }
    return {name: round(safe_float(value), 8) for name, value in values.items()}
