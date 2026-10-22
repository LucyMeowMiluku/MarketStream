from datetime import datetime, timedelta, timezone

from processing.event_models import FACTOR_GROUPS, MarketEvent
from processing.factor_engine import LightweightFactorEngine, market_session


BASE = datetime(2025, 1, 6, 15, 0, tzinfo=timezone.utc)


def _trade(ticker: str, when: datetime, price: float, size: int, event_id: str):
    return MarketEvent.create(
        event_id=event_id,
        source="test",
        feed="iex",
        event_type="trade",
        ticker=ticker,
        event_time=when,
        received_at=when,
        trade={"price": price, "size": size, "side": "buy"},
    )


def _quote(ticker: str, when: datetime, event_id: str):
    return MarketEvent.create(
        event_id=event_id,
        source="test",
        feed="iex",
        event_type="quote",
        ticker=ticker,
        event_time=when,
        received_at=when,
        quote={
            "bid_price": 99.0,
            "ask_price": 101.0,
            "bid_size": 10,
            "ask_size": 10,
        },
    )


def test_emits_three_cadences_with_eight_factors_and_input_summary():
    engine = LightweightFactorEngine(min_history_days=1)
    engine.process(_trade("AAPL", BASE, 100, 10, "one"))
    snapshots = engine.process(_trade("AAPL", BASE + timedelta(minutes=5), 101, 20, "two"))
    assert {snapshot.cadence for snapshot in snapshots} == {"10s", "1m", "5m"}
    for snapshot in snapshots:
        assert set(snapshot.factor_values) == set(FACTOR_GROUPS)
        assert set(snapshot.factor_states) == set(FACTOR_GROUPS)
        assert snapshot.source_event_ids == ["one"]
    five_minute = next(snapshot for snapshot in snapshots if snapshot.cadence == "5m")
    assert five_minute.input_summary["last_price"] == 100
    assert five_minute.input_summary["trade_volume"] == 10


def test_warmup_requires_five_distinct_trading_days_for_same_intraday_slot():
    engine = LightweightFactorEngine(cadences=(300,), min_history_days=5)
    emitted = []
    # return_surprise is only observed once five strictly-prior raw returns
    # exist; it then needs five strictly-prior days of its own history.
    for day in range(12):
        when = BASE + timedelta(days=day)
        emitted.extend(engine.process(_trade("AAPL", when, 100 + day, 100, f"d{day}")))
    assert emitted[-2].warmup_status == "warming_up"
    assert emitted[-1].warmup_status == "ready"
    assert emitted[-1].factor_states["return_surprise"]["history_days"] == 5


def test_warmup_return_scores_do_not_pollute_return_surprise_threshold():
    engine = LightweightFactorEngine(cadences=(300,), min_history_days=5)
    emitted = []
    for day in range(12):
        when = BASE + timedelta(days=day)
        price = 100.0 if day % 2 == 0 else 101.0
        emitted.extend(engine.process(_trade("AAPL", when, price, 100, f"d{day}")))
    recorded = [
        value
        for record in engine.export_baseline_state()["baselines"]
        if record["name"] == "return_surprise"
        for _, value in record["values"]
    ]
    # Before the raw-return scale exists the score would be ~1e4 here.
    assert recorded and max(abs(value) for value in recorded) < 50
    assert emitted[-1].factor_states["return_surprise"]["threshold"] < 50


def test_ticker_state_isolated_and_bounded():
    engine = LightweightFactorEngine(cadences=(10,), min_history_days=1, max_tickers=2)
    for index, ticker in enumerate(("AAPL", "TSLA", "NVDA")):
        engine.process(_trade(ticker, BASE + timedelta(seconds=index), 100, 1, ticker))
    assert engine.state_size["tickers"] == 2
    assert engine.state_size["windows"] <= 2


def test_duplicate_event_is_traced_but_not_double_counted():
    engine = LightweightFactorEngine(cadences=(10,), min_history_days=1)
    first = _trade("AAPL", BASE, 100, 10, "same")
    engine.process(first)
    duplicate = MarketEvent.from_dict({**first.to_dict(), "quality_flags": ["duplicate"]})
    engine.process(duplicate)
    snapshots = engine.process(_trade("AAPL", BASE + timedelta(seconds=10), 101, 1, "next"))
    assert snapshots[0].input_summary["trade_volume"] == 10
    assert "duplicate" in snapshots[0].data_quality["flags"]


def test_market_sessions_are_separate():
    assert market_session(datetime(2025, 1, 6, 13, 0, tzinfo=timezone.utc)) == "pre_market"
    assert market_session(datetime(2025, 1, 6, 15, 0, tzinfo=timezone.utc)) == "regular"
    assert market_session(datetime(2025, 1, 6, 22, 0, tzinfo=timezone.utc)) == "post_market"


def test_exported_thresholds_can_be_frozen_before_test_replay():
    training = LightweightFactorEngine(cadences=(300,), min_history_days=2)
    for day in range(4):
        training.process(
            _trade("AAPL", BASE + timedelta(days=day * 7), 100 + day, 100, f"train-{day}")
        )
    state = training.export_baseline_state()
    testing = LightweightFactorEngine(cadences=(300,), min_history_days=2)
    testing.import_baseline_state(state, freeze=True)
    before = testing.export_baseline_state()["baselines"]
    testing.process(_trade("AAPL", BASE + timedelta(days=35), 120, 500, "test-one"))
    snapshots = testing.process(
        _trade("AAPL", BASE + timedelta(days=42), 121, 500, "test-two")
    )
    after = testing.export_baseline_state()["baselines"]
    assert before == after
    assert testing.frozen_baselines
    assert snapshots[0].baseline_version.startswith("frozen-mad-v4:")


def test_baseline_series_overwrites_same_day_and_keeps_latest_twenty():
    from datetime import date

    from processing.factor_state import BaselineSeries

    series = BaselineSeries(20)
    for day in range(1, 22):
        series.add(date(2025, 1, day), float(day))
    series.add(date(2025, 1, 21), 999.0)
    series.add(date(2025, 1, 1), -1.0)
    assert len(series.values) == 20
    assert series.values[0][0] == date(2025, 1, 2)
    assert series.values[-1] == (date(2025, 1, 21), 999.0)


def test_current_session_date_is_strictly_excluded_from_scoring():
    from datetime import date

    from processing.factor_state import BaselineSeries

    series = BaselineSeries(20)
    series.add(date(2025, 1, 1), 1.0)
    series.add(date(2025, 1, 2), 1000.0)
    median, *_ = series.summary(before=date(2025, 1, 2))
    assert median == 1.0


def test_quote_only_window_persists_retained_previous_close():
    engine = LightweightFactorEngine(
        cadences=(10,), epoch_id="epoch", track_state_updates=True
    )
    engine.process(_trade("AAPL", BASE, 100.0, 1, "trade"))
    engine.process(_quote("AAPL", BASE + timedelta(seconds=10), "quote-1"))
    engine.drain_state_updates()
    engine.process(_quote("AAPL", BASE + timedelta(seconds=20), "quote-2"))
    updates = engine.drain_state_updates()
    assert updates.runtime[-1].previous_close == 100.0


def test_out_of_order_window_is_not_degraded():
    # Out-of-order events are not accumulated, so they do not corrupt the
    # window; only CRITICAL_QUALITY_FLAGS degrade it (and suppress CEP alerts).
    engine = LightweightFactorEngine(cadences=(10,), min_history_days=1)
    engine.process(_trade("AAPL", BASE + timedelta(seconds=5), 100, 1, "first"))
    late = _trade("AAPL", BASE + timedelta(seconds=1), 99, 1, "late")
    engine.process(MarketEvent.from_dict({**late.to_dict(), "quality_flags": ["out_of_order"]}))
    snapshot = engine.process(_trade("AAPL", BASE + timedelta(seconds=10), 101, 1, "next"))[0]
    assert snapshot.data_quality["flags"] == ["out_of_order"]
    assert snapshot.data_quality["status"] == "good"


def _bar(interval_start: datetime, high: float, event_id: str):
    from processing.event_models import bar_timing

    timing = bar_timing(interval_start)
    return MarketEvent.create(
        event_id=event_id,
        source="test",
        feed="iex",
        event_type="bar",
        ticker="AAPL",
        event_time=timing["completed_at"],
        received_at=timing["completed_at"],
        bar={**timing["payload"], "open": 100, "high": high, "low": 99, "close": high, "volume": 50},
    )


def test_minute_bar_never_leaks_into_shorter_or_earlier_windows():
    engine = LightweightFactorEngine(cadences=(10, 60, 300), min_history_days=1)
    snapshots = []
    for event in (
        _trade("AAPL", BASE, 100, 1, "t0"),
        # The bar for [BASE, BASE+60s) has a high no trade reached; it completes
        # at BASE+60s, after the first 10 s window and exactly at the 1 m end.
        _bar(BASE, 150, "bar-0"),
        _trade("AAPL", BASE + timedelta(seconds=61), 100, 1, "t1"),
        _trade("AAPL", BASE + timedelta(seconds=75), 100, 1, "t2"),
    ):
        snapshots += engine.process(event)
    snapshots += engine.flush(BASE + timedelta(minutes=5))
    by_window = {(s.cadence, s.window_start): s for s in snapshots}
    assert by_window[("1m", BASE)].input_summary["bar_volume"] == 0
    # The bar is keyed into the windows that contain its completion time, but
    # neither the 10 s nor the 1 m window contains its whole interval.
    for key in (("10s", BASE + timedelta(seconds=60)), ("1m", BASE + timedelta(seconds=60))):
        summary = by_window[key].input_summary
        assert summary["event_type_counts"].get("bar") == 1
        assert summary["bar_volume"] == 0
        assert summary["first_price"] == 100  # the bar's close of 150 is not used
    # A 5 m window contains the whole minute, so the bar's range is used there.
    five_minutes = by_window[("5m", BASE)]
    assert five_minutes.input_summary["bar_volume"] == 50


def test_late_live_bar_lands_in_the_same_window_as_in_replay():
    def run(order):
        engine = LightweightFactorEngine(cadences=(300,), min_history_days=1)
        for event in order:
            engine.process(event)
        return engine.flush()[0].input_summary

    bar = _bar(BASE, 150, "bar-0")
    trade = _trade("AAPL", BASE + timedelta(seconds=61), 100, 1, "t1")
    # Replay sorts by event_time; live receives the bar a few seconds after the
    # trade that followed its completion.  Both keep the same window contents.
    assert run([bar, trade]) == run([trade, bar])


def test_return_scale_falls_back_to_mean_absolute_deviation_and_one_tick():
    from processing.factor_state import return_scale

    import pytest

    # MAD defined: the usual robust scale.
    assert return_scale([-0.002, 0.0, 0.002], 0.0, 0.002, 100.0) == pytest.approx(1.4826 * 0.002)
    # Most returns exactly zero: MAD is 0, so the mean absolute deviation is used.
    values = [0.0] * 15 + [0.001] * 5
    assert return_scale(values, 0.0, 0.0, 100.0) == pytest.approx(1.2533 * 0.00025)
    # Every return identical: the scale is one price tick as a return.
    assert return_scale([0.0] * 20, 0.0, 0.0, 200.0) == pytest.approx(0.01 / 200.0)
    # A tiny but positive spread is still never below one tick.
    assert return_scale([0.0, 1e-7, -1e-7], 0.0, 1e-7, 100.0) == pytest.approx(1e-4)


def test_mostly_flat_slot_does_not_inflate_return_surprise():
    engine = LightweightFactorEngine(cadences=(300,), min_history_days=5)
    emitted = []
    for day in range(13):
        when = BASE + timedelta(days=day)
        # The slot's close is unchanged on most days, as in thin 10 s windows.
        price = 100.0 if day % 4 else 100.05
        emitted.extend(engine.process(_trade("AAPL", when, price, 100, f"d{day}")))
    emitted.extend(engine.process(_trade("AAPL", BASE + timedelta(days=13), 100.06, 100, "move")))
    emitted.extend(engine.flush())
    assert emitted[-1].window_start.date() == (BASE + timedelta(days=13)).date()
    # A 1 bp move is a handful of typical moves, not the ~100 a 1e-6 floor gave.
    assert abs(emitted[-1].factor_values["return_surprise"]) < 20
