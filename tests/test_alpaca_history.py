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
