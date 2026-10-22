import json

import pytest

from replay.alpaca_history import (
    AlpacaHistoricalClient,
    news_row_to_events,
    stock_row_to_event,
)


class StubClient(AlpacaHistoricalClient):
    def __init__(self):
        super().__init__("key", "secret")
        self.calls = 0

    def iter_pages(self, path, params, *, row_key, initial_token=None):
        self.calls += 1
        yield [{"id": 1}], "next"
        yield [{"id": 2}], None


def test_quote_conversion_preserves_real_provenance_and_has_bounded_id():
    event = stock_row_to_event(
        "quote",
        "AAPL",
        {
            "t": "2025-01-06T15:00:00Z",
            "bp": 99.9,
            "ap": 100.1,
            "bs": 10,
            "as": 12,
            "bx": "V",
            "ax": "V",
        },
        dataset_id="reviewed-v1",
        interval_id="aapl-event",
        phase="evaluation",
    )
    assert event.source == "alpaca"
    assert event.mode == "replay_real"
    assert event.provenance["phase"] == "evaluation"
    assert len(event.event_id) < 64
    assert event.quote["bid_price"] == 99.9


def test_news_conversion_only_emits_requested_symbols():
    events = news_row_to_events(
        {
            "id": 123,
            "created_at": "2025-01-06T15:00:00Z",
            "headline": "AAPL gains after strong results",
            "symbols": ["AAPL", "MSFT"],
            "source": "benzinga",
        },
        symbols={"AAPL", "SPY"},
        dataset_id="reviewed-v1",
        interval_id="aapl-event",
        phase="evaluation",
    )
    assert [event.ticker for event in events] == ["AAPL"]
    assert events[0].news["sentiment_score"] > 0


def test_paginated_download_is_resumable(tmp_path):
    client = StubClient()
    output = tmp_path / "rows.jsonl"
    state = client.download_rows("/test", {}, row_key="rows", output=output)
    assert state["complete"] is True
    assert state["pages"] == 2
    assert [json.loads(line)["id"] for line in output.read_text().splitlines()] == [1, 2]
    client.download_rows("/test", {}, row_key="rows", output=output)
    assert client.calls == 1


def test_paginated_download_refuses_checkpoint_for_a_different_request(tmp_path):
    client = StubClient()
    output = tmp_path / "rows.jsonl"
    client.download_rows("/test", {"feed": "iex"}, row_key="rows", output=output)
    with pytest.raises(ValueError, match="checkpoint request"):
        client.download_rows("/test", {"feed": "sip"}, row_key="rows", output=output)


BAR_ROW = {"t": "2025-01-06T15:00:00Z", "o": 100.0, "h": 105.0, "l": 99.0, "c": 104.0, "v": 900, "n": 12, "vw": 102.0}


def test_bar_conversion_keys_by_completion_and_keeps_interval():
    event = stock_row_to_event(
        "bar", "AAPL", BAR_ROW, dataset_id="reviewed-v1", interval_id="aapl-event", phase="evaluation"
    )
    assert event.event_time.isoformat() == "2025-01-06T15:01:00+00:00"
    assert event.bar["interval_start"] == "2025-01-06T15:00:00+00:00"
    assert event.bar["interval_end"] == "2025-01-06T15:01:00+00:00"
    assert event.bar["timeframe"] == "1Min"
    # The historical API has no publication time: arrival is assumed, and said so.
    assert event.received_at == event.event_time
    assert event.provenance["received_at_basis"] == "assumed_at_completion"
    assert event.provenance["converter_version"] == "alpaca-market-event-v2"


def test_live_and_historical_bars_share_timing_semantics():
    from datetime import datetime, timezone

    from producers.alpaca_producer import _stock_event

    live = _stock_event({"T": "b", "S": "AAPL", **BAR_ROW})
    replay = stock_row_to_event(
        "bar", "AAPL", BAR_ROW, dataset_id="reviewed-v1", interval_id="aapl-event", phase="evaluation"
    )
    assert live.event_time == replay.event_time
    fields = ("interval_start", "interval_end", "timeframe", "open", "high", "low", "close", "volume")
    assert {name: live.bar[name] for name in fields} == {name: replay.bar[name] for name in fields}
    # Live arrival is observed, never earlier than completion in practice.
    assert live.received_at <= datetime.now(timezone.utc)
    # Daily and corrected bars are not part of the contract.
    assert _stock_event({"T": "d", "S": "AAPL", **BAR_ROW}) is None
    assert _stock_event({"T": "u", "S": "AAPL", **BAR_ROW}) is None
