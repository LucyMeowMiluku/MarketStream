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


def test_emits_three_cadences_with_eight_factors_and_legacy_summary():
    engine = LightweightFactorEngine(min_history_days=1)
    engine.process(_trade("AAPL", BASE, 100, 10, "one"))
    snapshots = engine.process(_trade("AAPL", BASE + timedelta(minutes=5), 101, 20, "two"))
    assert {snapshot.cadence for snapshot in snapshots} == {"10s", "1m", "5m"}
    for snapshot in snapshots:
        assert set(snapshot.factor_values) == set(FACTOR_GROUPS)
        assert set(snapshot.factor_states) == set(FACTOR_GROUPS)
        assert snapshot.source_event_ids == ["one"]
    five_minute = next(snapshot for snapshot in snapshots if snapshot.cadence == "5m")
    assert five_minute.legacy_features["avg_close"] == 100
    assert five_minute.legacy_features["total_volume"] == 10


def test_warmup_requires_five_distinct_trading_days_for_same_intraday_slot():
    engine = LightweightFactorEngine(cadences=(300,), min_history_days=5)
    last = []
    # Six completed days are needed so the sixth can be judged against five
    # strictly-prior days without leaking the current window into its threshold.
    for day in range(7):
        when = BASE + timedelta(days=day * 7, minutes=day * 0)
        last = engine.process(_trade("AAPL", when, 100 + day, 100, f"d{day}"))
    assert last[0].warmup_status == "ready"
    assert last[0].factor_states["return_surprise"]["history_days"] >= 5


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
    assert snapshots[0].legacy_features["total_volume"] == 10
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
    assert snapshots[0].baseline_version.startswith("frozen-mad-v1:")
