from datetime import datetime, timedelta, timezone

from processing.data_quality import EventQualityGate
from processing.event_models import MarketEvent


NOW = datetime(2025, 1, 6, 15, 0, tzinfo=timezone.utc)


def _event(event_id: str, event_time: datetime, **trade):
    return MarketEvent.create(
        event_id=event_id,
        source="test",
        feed="iex",
        event_type="trade",
        ticker="AAPL",
        event_time=event_time,
        received_at=NOW,
        trade={"price": 100.0, "size": 1, **trade},
    )


def test_duplicate_out_of_order_zero_volume_and_stale_flags():
    gate = EventQualityGate(stale_after=timedelta(seconds=5))
    gate.assess(_event("one", NOW), now=NOW)
    duplicate = gate.assess(_event("one", NOW - timedelta(seconds=1), size=0), now=NOW)
    assert {"duplicate", "out_of_order", "zero_volume"}.issubset(duplicate.quality_flags)

    stale = gate.assess(_event("two", NOW - timedelta(seconds=10)), now=NOW)
    assert "stale" in stale.quality_flags
    replay = EventQualityGate(stale_after=timedelta(seconds=5)).assess(
        _event("three", NOW - timedelta(days=30)), mode="replay", now=NOW
    )
    assert "stale" not in replay.quality_flags


def test_crossed_quote_and_feed_gap_are_explicit():
    gate = EventQualityGate(gap_after=timedelta(seconds=5))
    first = MarketEvent.create(
        event_id="q1",
        source="test",
        feed="iex",
        event_type="quote",
        ticker="AAPL",
        event_time=NOW,
        received_at=NOW,
        quote={"bid_price": 101, "ask_price": 100, "bid_size": 1, "ask_size": 1},
    )
    assert "crossed_quote" in gate.assess(first, now=NOW).quality_flags
    second = MarketEvent.create(
        event_id="q2",
        source="test",
        feed="iex",
        event_type="quote",
        ticker="AAPL",
        event_time=NOW + timedelta(seconds=10),
        received_at=NOW + timedelta(seconds=10),
        quote={"bid_price": 100, "ask_price": 101, "bid_size": 1, "ask_size": 1},
    )
    assert "feed_gap" in gate.assess(second, now=second.event_time).quality_flags


def test_live_minute_bar_staleness_is_measured_from_completion():
    from processing.event_models import bar_timing

    gate = EventQualityGate(stale_after=timedelta(seconds=5))

    def bar(event_id, interval_start):
        timing = bar_timing(interval_start)
        return MarketEvent.create(
            event_id=event_id,
            source="alpaca",
            feed="iex",
            event_type="bar",
            ticker="AAPL",
            event_time=timing["completed_at"],
            received_at=NOW,
            bar={**timing["payload"], "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 10},
        )

    # The minute [NOW-62s, NOW-2s) completed 2 s ago: fresh, not stale.
    assert "stale" not in gate.assess(bar("bar-recent", NOW - timedelta(seconds=62)), now=NOW).quality_flags
    # Completed 10 s ago with a 5 s limit: stale, with no extra bar grace.
    assert "stale" in gate.assess(bar("bar-old", NOW - timedelta(seconds=70)), now=NOW).quality_flags


def test_seen_id_memory_is_bounded():
    gate = EventQualityGate(max_seen_ids=2, max_state_keys=2)
    for index in range(3):
        gate.assess(_event(str(index), NOW + timedelta(seconds=index)), now=NOW)
    assert gate.seen_count == 2
    assert gate.state_key_count <= 2
