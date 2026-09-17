from datetime import datetime, timezone

import pytest

from processing.event_models import EventType, FactorSnapshot, MarketEvent


NOW = datetime(2025, 1, 6, 15, 0, tzinfo=timezone.utc)


def test_market_event_round_trip_and_deterministic_id():
    first = MarketEvent.create(
        source="test",
        feed="iex",
        event_type="trade",
        ticker="aapl",
        event_time=NOW,
        received_at=NOW,
        trade={"price": 100.0, "size": 10},
    )
    second = MarketEvent.create(
        source="test",
        feed="iex",
        event_type=EventType.TRADE,
        ticker="AAPL",
        event_time=NOW,
        received_at=NOW,
        trade={"price": 100.0, "size": 10},
    )
    assert first.event_id == second.event_id
    assert first.ticker == "AAPL"
    assert MarketEvent.from_dict(first.to_dict()).to_dict() == first.to_dict()


def test_market_event_rejects_mismatched_payload():
    with pytest.raises(ValueError, match="does not match"):
        MarketEvent(
            event_id="bad",
            source="test",
            feed="iex",
            event_type=EventType.TRADE,
            ticker="AAPL",
            event_time=NOW,
            received_at=NOW,
            quote={"bid_price": 99, "ask_price": 100},
        )


def test_factor_snapshot_round_trip():
    snapshot = FactorSnapshot(
        ticker="AAPL",
        event_time=NOW,
        cadence="10s",
        factor_values={"return_surprise": 1.2},
        factor_states={"return_surprise": {"state": "normal"}},
        baseline_version="v1",
        data_quality={"status": "good"},
        warmup_status="ready",
        source_event_ids=["one"],
        window_start=NOW,
        input_summary={"last_price": 100.0},
    )
    assert FactorSnapshot.from_dict(snapshot.to_dict()).to_dict() == snapshot.to_dict()
