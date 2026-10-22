"""Measurements for human label review (docs/LABELING_CRITERIA.md).

Pure functions over consolidated SIP 1-minute bars.  These numbers describe the
market for reviewers; they never come from, or feed, the detector.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
REGULAR_OPEN, REGULAR_CLOSE = time(9, 30), time(16, 0)
REFERENCE_SESSIONS = 20
SINGLE_STOCK_FLOOR, ETF_FLOOR = 0.010, 0.005
ETFS = {"SPY", "QQQ"}
BENCHMARK = "QQQ"

# Thresholds from docs/LABELING_CRITERIA.md; displayed next to the measured
# values, never turned into a label by the tool.
THRESHOLDS = {
    "anomaly_move_ratio": 4.0,
    "anomaly_volume_ratio": 2.0,
    "normal_ratio": 1.5,
    "gap_retrace": 0.5,
    "min_coverage": 0.95,
}


@dataclass(frozen=True, slots=True)
class Bar:
    start: datetime  # New York time, minute start
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class WindowStats:
    reference_price: float
    open_price: float
    end_price: float
    gap: float
    in_window: float
    total: float
    range: float
    volume: float
    minutes_present: int
    minutes_expected: int

    @property
    def coverage(self) -> float:
        return self.minutes_present / self.minutes_expected if self.minutes_expected else 0.0


def regular_bars(bars: list[Bar]) -> dict[date, list[Bar]]:
    """Group regular-session bars by New York session date."""

    sessions: dict[date, list[Bar]] = {}
    for bar in sorted(bars, key=lambda item: item.start):
        if REGULAR_OPEN <= bar.start.time() < REGULAR_CLOSE:
            sessions.setdefault(bar.start.date(), []).append(bar)
    return sessions


def window_stats(
    sessions: dict[date, list[Bar]],
    day: date,
    start: time,
    end: time,
) -> WindowStats | None:
    """Measure one clock window; None when the window or its reference is missing."""

    bars = [bar for bar in sessions.get(day, []) if start <= bar.start.time() < end]
    if not bars:
        return None
    if start == REGULAR_OPEN:
        previous = [item for item in sorted(sessions) if item < day]
        if not previous:
            return None
        reference = sessions[previous[-1]][-1].close  # last regular bar: handles half days
    else:
        before = [bar for bar in sessions[day] if bar.start.time() < start]
        if not before:
            return None
        reference = before[-1].close
    open_price, end_price = bars[0].open, bars[-1].close
    expected = int(
        (datetime.combine(day, end) - datetime.combine(day, start)).total_seconds() // 60
    )
    return WindowStats(
        reference_price=reference,
        open_price=open_price,
        end_price=end_price,
        gap=open_price / reference - 1,
        in_window=end_price / open_price - 1,
        total=end_price / reference - 1,
        range=(max(bar.high for bar in bars) - min(bar.low for bar in bars)) / reference,
        volume=sum(bar.volume for bar in bars),
        minutes_present=len({bar.start for bar in bars}),
        minutes_expected=expected,
    )


def _median_abs(values: list[float]) -> float | None:
    return statistics.median(abs(value) for value in values) if values else None


def _ratio(value: float, typical: float | None) -> float | None:
    return abs(value) / typical if typical else None


def interval_measurements(
    bars_by_symbol: dict[str, dict[date, list[Bar]]],
    ticker: str,
    day: date,
    start: time,
    end: time,
) -> dict[str, Any]:
    """Today's values, the 20-session typical values and ratios for one interval."""

    calendar = sorted(bars_by_symbol["SPY"])  # SPY trades every regular session
    prior = [item for item in calendar if item < day][-REFERENCE_SESSIONS:]
    symbols = [ticker] + [item for item in ("SPY", "QQQ") if item != ticker]
    result: dict[str, Any] = {
        "ticker": ticker,
        "date": day.isoformat(),
        "window": [start.strftime("%H:%M"), end.strftime("%H:%M")],
        "reference_sessions": [item.isoformat() for item in prior],
        "symbols": {},
    }
    stats_today = {}
    for symbol in symbols:
        sessions = bars_by_symbol[symbol]
        today = window_stats(sessions, day, start, end)
        history = [window_stats(sessions, item, start, end) for item in prior]
        history = [item for item in history if item is not None]
        stats_today[symbol] = (today, history)
        if today is None:
            result["symbols"][symbol] = {"available": False}
            continue
        typical = {
            "total": _median_abs([item.total for item in history]),
            "in_window": _median_abs([item.in_window for item in history]),
            "gap": _median_abs([item.gap for item in history]),
            "range": _median_abs([item.range for item in history]),
            "volume": _median_abs([item.volume for item in history]),
        }
        result["symbols"][symbol] = {
            "available": True,
            "today": {**asdict(today), "coverage": today.coverage},
            "typical": typical,
            "history_sessions": len(history),
            "ratios": {
                "move": _ratio(today.total, typical["total"]),
                "range": _ratio(today.range, typical["range"]),
                "volume": _ratio(today.volume, typical["volume"]),
            },
        }
    if ticker not in ETFS:
        today, bench_today = stats_today[ticker][0], stats_today[BENCHMARK][0]
        excess_history = []
        for item in prior:
            own = window_stats(bars_by_symbol[ticker], item, start, end)
            bench = window_stats(bars_by_symbol[BENCHMARK], item, start, end)
            if own and bench:
                excess_history.append(own.total - bench.total)
        if today and bench_today:
            excess = today.total - bench_today.total
            typical_excess = _median_abs(excess_history)
            result["excess_vs_qqq"] = {
                "today": excess,
                "typical": typical_excess,
                "ratio": _ratio(excess, typical_excess),
            }
    return result


def rule_inputs(measurement: dict[str, Any]) -> dict[str, Any]:
    """Values each criterion refers to, side by side with its threshold.

    This only arranges numbers for the reviewer; it does not combine them into
    a decision, and catalyst/news/macro rules (A3, N4, N5) are left to the
    reviewer entirely.
    """

    ticker = measurement["ticker"]
    own = measurement["symbols"].get(ticker, {})
    if not own.get("available"):
        return {"available": False}
    today, ratios = own["today"], own["ratios"]
    floor = ETF_FLOOR if ticker in ETFS else SINGLE_STOCK_FLOOR
    market = {
        symbol: value["ratios"]["move"]
        for symbol, value in measurement["symbols"].items()
        if symbol != ticker and value.get("available")
    }
    coverage = {
        symbol: value["today"]["coverage"]
        for symbol, value in measurement["symbols"].items()
        if value.get("available")
    }
    gap, in_window = today["gap"], today["in_window"]
    return {
        "available": True,
        "move_ratio": ratios["move"],
        "abs_total_move": abs(today["total"]),
        "move_floor": floor,
        "volume_ratio": ratios["volume"],
        "range_ratio": ratios["range"],
        "market_move_ratios": market,
        "gap": gap,
        "in_window": in_window,
        "direction_conflict": (
            gap * in_window < 0 and abs(in_window) >= THRESHOLDS["gap_retrace"] * abs(gap)
        ),
        "total_move_sign": "up" if today["total"] > 0 else "down" if today["total"] < 0 else "flat",
        "coverage": coverage,
        "excess_ratio": measurement.get("excess_vs_qqq", {}).get("ratio"),
    }


def parse_bar(row: dict[str, Any]) -> Bar:
    start = datetime.fromisoformat(row["t"].replace("Z", "+00:00")).astimezone(NY)
    return Bar(start, row["o"], row["h"], row["l"], row["c"], row["v"])


def fetch_sip_bars(client, symbols: list[str], start: date, end: date) -> dict[str, list[Bar]]:
    """Fetch consolidated SIP 1-minute bars (all pages) for a date range."""

    params = {
        "symbols": ",".join(symbols),
        "timeframe": "1Min",
        "start": datetime.combine(start, time(0), NY).isoformat(),
        "end": (datetime.combine(end, time(0), NY) + timedelta(days=1)).isoformat(),
        "feed": "sip",
        "adjustment": "split",
        "limit": 10_000,
        "sort": "asc",
    }
    result: dict[str, list[Bar]] = {symbol: [] for symbol in symbols}
    token = None
    while True:
        payload = client.request_json("/v2/stocks/bars", {**params, "page_token": token})
        for symbol, rows in (payload.get("bars") or {}).items():
            result[symbol].extend(parse_bar(row) for row in rows)
        token = payload.get("next_page_token")
        if not token:
            return result
