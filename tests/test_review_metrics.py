from datetime import date, datetime, time, timedelta

import pytest

from replay.review_metrics import NY, Bar, interval_measurements, regular_bars, rule_inputs, window_stats


def _session(day: date, prices: list[float], *, volume: float = 100, close_at: time = time(16, 0)):
    """One regular session of 1-minute bars; prices[i] is the close of minute i."""

    start = datetime.combine(day, time(9, 30), NY)
    minutes = int((datetime.combine(day, close_at) - datetime.combine(day, time(9, 30))).seconds // 60)
    bars, previous = [], prices[0]
    for index in range(minutes):
        close = prices[min(index, len(prices) - 1)]
        bars.append(Bar(start + timedelta(minutes=index), previous, max(previous, close),
                        min(previous, close), close, volume))
        previous = close
    return bars


def test_window_stats_measure_gap_move_range_volume_and_coverage():
    day1, day2 = date(2024, 1, 2), date(2024, 1, 3)
    bars = _session(day1, [100.0]) + _session(day2, [110.0] * 30 + [104.5])
    sessions = regular_bars(bars)
    stats = window_stats(sessions, day2, time(9, 30), time(11, 0))
    assert stats.reference_price == 100.0
    assert stats.gap == pytest.approx(0.10)  # opens at 110 against a 100 close
    assert stats.in_window == pytest.approx(104.5 / 110 - 1)
    assert stats.total == pytest.approx(0.045)
    assert stats.range == pytest.approx(0.055)
    assert stats.volume == 9000
    assert stats.coverage == 1.0


def test_half_day_reference_uses_last_regular_bar():
    early_close = _session(date(2024, 7, 3), [100.0, 101.0], close_at=time(13, 0))
    sessions = regular_bars(early_close + _session(date(2024, 7, 5), [101.0]))
    assert window_stats(sessions, date(2024, 7, 5), time(9, 30), time(11, 0)).reference_price == 101.0


def test_ratios_compare_with_same_window_over_twenty_prior_sessions():
    days = [date(2024, 1, 2) + timedelta(days=offset) for offset in range(22)]
    bars = {symbol: [] for symbol in ("AAPL", "SPY", "QQQ")}
    price = {symbol: 100.0 for symbol in bars}
    for index, day in enumerate(days):
        last = index == len(days) - 1
        moved = 1.08 if last else (1.01 if index % 2 else 0.99)
        for symbol in bars:
            factor = moved if symbol == "AAPL" else 1.0
            start, price[symbol] = price[symbol], price[symbol] * factor
            volume = 300 if last and symbol == "AAPL" else 100
            # No gap: each session opens at the previous close.
            bars[symbol] += _session(day, [start] * 5 + [price[symbol]], volume=volume)
    sessions = {symbol: regular_bars(items) for symbol, items in bars.items()}
    measured = interval_measurements(sessions, "AAPL", days[-1], time(9, 30), time(11, 0))
    assert len(measured["reference_sessions"]) == 20
    ratios = measured["symbols"]["AAPL"]["ratios"]
    assert ratios["move"] == pytest.approx(8.0)  # 8% against a typical 1%
    assert ratios["volume"] == pytest.approx(3.0)
    inputs = rule_inputs(measured)
    assert inputs["total_move_sign"] == "up"
    assert inputs["direction_conflict"] is False
    assert inputs["excess_ratio"] == pytest.approx(8.0)
    # The helper arranges numbers only; it never emits a label or decision.
    assert not {"label", "kind", "decision"} & set(inputs)


def test_direction_conflict_when_window_gives_back_half_the_gap():
    day1, day2 = date(2024, 1, 2), date(2024, 1, 3)
    # Opens +10% (first bar opens at 110 because its first close is 110) and ends at +4%.
    sessions = regular_bars(_session(day1, [100.0]) + _session(day2, [110.0] * 2 + [104.0]))
    stats = window_stats(sessions, day2, time(9, 30), time(11, 0))
    measured = {"ticker": "SPY", "symbols": {"SPY": {"available": True, "today": {
        "gap": 0.10, "in_window": stats.in_window, "total": stats.total, "coverage": 1.0},
        "ratios": {"move": 5, "range": 5, "volume": 3}}}}
    assert rule_inputs(measured)["direction_conflict"] is True
